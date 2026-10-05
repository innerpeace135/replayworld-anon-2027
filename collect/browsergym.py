from __future__ import annotations

import asyncio
import importlib
import re
import threading
from collections.abc import Callable

from replayworld.config import load_config
from replayworld.llm import LanguageModel, with_scheme
from replayworld.prompts import prompt

from .common import arguments, load_queries, save, trace_row

SOURCE = "browsergym"
STEP_CAP = 8
PAGE_CHARS = 8000
PAGE_LOAD_WAIT = "noop(5000)"
ACTION_NAMES = r"(?:click|fill|scroll|go_back|go_forward|noop|goto|new_tab|tab_focus|tab_close|send_msg_to_user)"
LABELED_ACTION = re.compile(rf"[Aa]ction:\s*({ACTION_NAMES}\s*\(.*)")
BARE_ACTION = re.compile(rf"^({ACTION_NAMES}\s*\(.*)")


def parse_action(reply: str) -> str:
    lines = [line.strip() for line in reversed(reply.strip().splitlines())]
    for pattern in (LABELED_ACTION, BARE_ACTION):
        for line in lines:
            match = pattern.match(line)
            if match:
                return match.group(1).strip()
    return "noop()"


def page(observation: dict) -> str:
    from browsergym.utils.obs import flatten_axtree_to_str

    return flatten_axtree_to_str(observation["axtree_object"])


def collect_trace(index: int, task: str, ask: Callable[[list[dict]], str], start_url: str) -> dict:
    import gymnasium

    importlib.import_module("browsergym.core")
    environment = gymnasium.make("browsergym/openended", task_kwargs={"start_url": start_url, "goal": task})
    try:
        observation, _ = environment.reset()
        observation, _, _, _, _ = environment.step(PAGE_LOAD_WAIT)
        pages = [page(observation)]
        messages = [{"role": "system", "content": prompt("collect/browsergym_agent", goal=task)}]
        actions: list[str] = []
        for _ in range(STEP_CAP):
            messages.append({"role": "user", "content": f"Current page:\n{pages[-1][:PAGE_CHARS]}"})
            reply = ask(messages)
            messages.append({"role": "assistant", "content": reply})
            actions.append(parse_action(reply))
            observation, _, terminated, truncated, _ = environment.step(actions[-1])
            pages.append(page(observation))
            if terminated or truncated:
                break
    finally:
        environment.close()
    steps = [{"action": action, "observation": text[:PAGE_CHARS]} for action, text in zip(actions, pages[1:])]
    clipped = len(pages[-1]) > PAGE_CHARS
    return trace_row(SOURCE, index, task, pages[0][:PAGE_CHARS], steps, 0.0, clipped)


def collect(config_path: str, queries_path: str, output: str, limit: int | None, start_url: str) -> int:
    model = LanguageModel(load_config(config_path).agent)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    def ask(messages: list[dict]) -> str:
        future = asyncio.run_coroutine_threadsafe(model.reply(messages, temperature=0.0, max_tokens=400), loop)
        return future.result().text

    rows = []
    for index, task in enumerate(load_queries(queries_path, limit)):
        try:
            rows.append(collect_trace(index, task, ask, start_url))
        except Exception as error:
            print(f"{SOURCE}-{index:05d}: skipped ({error!r})")
    loop.call_soon_threadsafe(loop.stop)
    thread.join()
    loop.close()
    return save(output, rows)


def main() -> None:
    parser = arguments("Collect traces from a live commerce site through BrowserGym.")
    parser.add_argument("--start_url", default="www.target.com")
    options = parser.parse_args()
    kept = collect(
        options.config, options.queries, options.output, options.limit, with_scheme(options.start_url, "https")
    )
    print(f"{SOURCE}: {kept} traces")


if __name__ == "__main__":
    main()
