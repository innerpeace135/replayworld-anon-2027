from __future__ import annotations

import json
from pathlib import Path

from replayworld.config import resolve

from .common import arguments, save, subset, trace_row

SOURCE = "toolbench"
FINISH = "Finish"


def convert(answer: dict, index: int) -> dict | None:
    generation = answer.get("answer_generation") or {}
    conversations = generation.get("train_messages") or []
    if not generation.get("valid_data") or not conversations:
        return None
    steps: list[dict] = []
    messages = conversations[-1]
    for position, message in enumerate(messages[:-1]):
        call = message.get("function_call")
        response = messages[position + 1]
        if message.get("role") != "assistant" or not call or call.get("name") == FINISH:
            continue
        if response.get("role") != "function":
            continue
        thought = (message.get("content") or "").strip()
        action = f"Action: {call['name']}\nAction Input: {call.get('arguments', '')}"
        steps.append(
            {
                "action": f"Thought: {thought}\n{action}" if thought else action,
                "observation": response.get("content") or "",
            }
        )
    task = (generation.get("query") or "").strip()
    return trace_row(SOURCE, index, task, "", steps, 1.0 if answer.get("win") else 0.0) if task else None


def collect(answers: str, output: str, sample: int | None, seed: int) -> int:
    files = sorted(Path(resolve(answers)).rglob("*.json"))
    rows = []
    for index in subset(len(files), sample, seed):
        rows.append(convert(json.loads(files[index].read_text(encoding="utf-8")), index))
    return save(output, rows)


def main() -> None:
    parser = arguments("Convert released ToolBench trajectories into traces.", queries=False)
    parser.add_argument("--answers", required=True)
    options = parser.parse_args()
    print(f"{SOURCE}: {collect(options.answers, options.output, options.sample, options.seed)} traces")


if __name__ == "__main__":
    main()
