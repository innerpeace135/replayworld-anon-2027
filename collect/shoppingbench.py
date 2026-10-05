from __future__ import annotations

import asyncio
import json

import httpx

from replayworld.config import load_config
from replayworld.llm import LanguageModel, with_scheme
from replayworld.prompts import load_prompt

from .common import arguments, load_queries, save, trace_row

SOURCE = "shoppingbench"
STEP_CAP = 20
RESULT_CHARS = 5000
TERMINAL = "recommend_product"
SEARCH = "find_product"
API_TOOLS = (SEARCH, "view_product_information")
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": SEARCH,
            "description": "Search for products. Returns up to 10 products with product_id, shop_id, title, price, service, sold_count.",
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Search query keywords"},
                    "page": {"type": "integer", "description": "Page number (1-5)", "default": 1},
                    "price": {"type": "string", "description": "Price range, e.g. '0-50', '50-100'"},
                    "sort": {
                        "type": "string",
                        "enum": ["priceasc", "pricedesc", "order", "default"],
                        "default": "default",
                    },
                },
                "required": ["q"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_product_information",
            "description": "Get detailed product information including description, SKU options, and attributes.",
            "parameters": {
                "type": "object",
                "properties": {"product_ids": {"type": "string", "description": "Comma-separated product IDs"}},
                "required": ["product_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TERMINAL,
            "description": "Recommend the found product to the user. Call this when you've found the right product.",
            "parameters": {
                "type": "object",
                "properties": {"product_ids": {"type": "string", "description": "Product ID(s) to recommend"}},
                "required": ["product_ids"],
            },
        },
    },
]


async def request(client: httpx.AsyncClient, server: str, name: str, call: dict) -> str | None:
    params = {key: value for key, value in call.items() if value}
    if name == SEARCH:
        params.setdefault("page", 1)
    try:
        response = await client.get(f"{server}/{name}", params=params)
    except httpx.HTTPError:
        return None
    return None if response.is_error else response.text


async def collect_trace(
    index: int, task: str, model: LanguageModel, client: httpx.AsyncClient, server: str
) -> dict | None:
    messages = [
        {"role": "system", "content": load_prompt("collect/shoppingbench_agent")},
        {"role": "user", "content": task},
    ]
    steps: list[dict] = []
    recommended = failed = clipped = False
    for _ in range(STEP_CAP):
        reply = await model.reply(messages, tools=TOOLS, temperature=0.0)
        messages.append(reply.message())
        if not reply.tool_calls:
            messages.append({"role": "user", "content": load_prompt("collect/shoppingbench_reminder")})
            continue
        for call in reply.tool_calls:
            if call.name == TERMINAL:
                recommended = True
                result = json.dumps({"status": "recommended"})
            elif call.name in API_TOOLS:
                observation = await request(client, server, call.name, call.arguments)
                if observation is None:
                    failed = True
                    break
                result = observation[:RESULT_CHARS]
                clipped = len(observation) > RESULT_CHARS
                action = f"{call.name}({json.dumps(call.arguments, ensure_ascii=False)})"
                steps.append({"action": action, "observation": result})
            else:
                result = json.dumps({"error": f"Unknown tool: {call.name}"})
            messages.append({"role": "tool", "tool_call_id": call.call_id, "content": result})
        if recommended or failed:
            break
    if failed:
        return None
    return trace_row(SOURCE, index, task, "", steps, 1.0 if recommended else 0.0, clipped)


async def collect(config_path: str, queries_path: str, output: str, limit: int | None, server: str) -> int:
    model = LanguageModel(load_config(config_path).agent)
    queries = load_queries(queries_path, limit)
    async with httpx.AsyncClient(timeout=30) as client:
        rows = await asyncio.gather(
            *[collect_trace(index, task, model, client, server.rstrip("/")) for index, task in enumerate(queries)],
            return_exceptions=True,
        )
    failures = [row for row in rows if isinstance(row, Exception)]
    if failures:
        print(f"{SOURCE}: {len(failures)} queries failed, first error: {failures[0]!r}")
    return save(output, [row for row in rows if isinstance(row, dict)])


def main() -> None:
    parser = arguments("Collect traces through the ShoppingBench API.")
    parser.add_argument("--server", required=True)
    options = parser.parse_args()
    server = with_scheme(options.server)
    kept = asyncio.run(collect(options.config, options.queries, options.output, options.limit, server))
    print(f"{SOURCE}: {kept} traces")


if __name__ == "__main__":
    main()
