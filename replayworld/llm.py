from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field

from openai import APIError, AsyncOpenAI, BadRequestError

from .config import ModelConfig


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: dict


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)

    def message(self) -> dict:
        message = {"role": "assistant", "content": self.text}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
                }
                for call in self.tool_calls
            ]
        return message


CONTEXT_OVERFLOW = re.compile(
    r"maximum context length is (\d+) tokens.*?(?:has (\d+) input tokens|\((\d+) in the messages)", re.S
)


def room_in_context(error: str) -> int | None:
    overflow = CONTEXT_OVERFLOW.search(error)
    return int(overflow.group(1)) - int(overflow.group(2) or overflow.group(3)) if overflow else None


def with_scheme(address: str, scheme: str = "") -> str:
    if not address or "://" in address:
        return address
    scheme = scheme or ("http" if address.startswith(("localhost", "127.")) else "https")
    return f"{scheme}://{address}"


class LanguageModel:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = AsyncOpenAI(
            base_url=with_scheme(config.api_base) or None,
            api_key=config.api_key or "EMPTY",
            timeout=config.timeout,
            max_retries=config.retries,
        )
        self.gate = asyncio.Semaphore(config.concurrency)

    async def reply(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        thinking: bool | None = False,
    ) -> Reply:
        budget = self.config.max_tokens if max_tokens is None else max_tokens
        budget_key = "max_completion_tokens" if self.config.reasoning_effort else "max_tokens"
        request = {"model": self.config.model, "messages": messages, budget_key: budget}
        if self.config.reasoning_effort:
            request["reasoning_effort"] = self.config.reasoning_effort
        else:
            request["temperature"] = self.config.temperature if temperature is None else temperature
        if thinking is not None:
            request["extra_body"] = {"chat_template_kwargs": {"enable_thinking": thinking}}
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        async with self.gate:
            try:
                response = await self.client.chat.completions.create(**request)
            except BadRequestError as error:
                room = room_in_context(str(error))
                if room is None or not 0 < room < budget:
                    raise
                response = await self.client.chat.completions.create(**{**request, budget_key: room})
        return parse_reply(response.choices[0])

    async def complete(self, prompt: str, **decoding) -> str:
        return (await self.reply([{"role": "user", "content": prompt}], **decoding)).text


async def preflight(model, role: str, tools: list[dict] | None = None, thinking: bool | None = None) -> None:
    try:
        await model.reply([{"role": "user", "content": "ping"}], tools=tools, max_tokens=16, thinking=thinking)
    except APIError as error:
        address = model.config.api_base or "(api_base not set)"
        raise SystemExit(
            f"the {role} endpoint {address} (model {model.config.model}) failed a test request: {error}"
        ) from None


def parse_reply(choice) -> Reply:
    calls = []
    for call in choice.message.tool_calls or []:
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except json.JSONDecodeError:
            arguments = {}
        calls.append(ToolCall(call.id, call.function.name, arguments if isinstance(arguments, dict) else {}))
    return Reply((choice.message.content or "").strip(), calls)


def parse_json(text: str) -> dict | None:
    decoder = json.JSONDecoder(strict=False)
    for start, character in enumerate(text):
        if character == "{":
            try:
                return decoder.raw_decode(text, start)[0]
            except json.JSONDecodeError:
                continue
    return None
