from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CLIP_CHARS = 200000


@dataclass
class Trace:
    trace_id: str
    task: str
    observations: list[str]
    actions: list[str]
    reward: float = 0.0
    final: bool = False
    clipped: bool = False
    free_running: bool = False

    def __post_init__(self):
        if len(self.observations) != len(self.actions) + 1 or not self.actions:
            raise ValueError(f"trace {self.trace_id} must hold T >= 1 actions and T + 1 observations")

    @property
    def length(self) -> int:
        return len(self.actions)

    def recorded(self, t: int) -> str:
        return self.observations[t + 1]

    @classmethod
    def from_row(cls, row: dict) -> Trace:
        return cls(
            trace_id=str(row["id"]),
            task=row["task"],
            observations=[row.get("initial_observation", "")] + [step["observation"] for step in row["steps"]],
            actions=[step["action"] for step in row["steps"]],
            reward=float(row.get("reward", 0.0)),
            final=bool(row.get("final", False)),
            clipped=bool(row.get("clipped", False)),
            free_running=bool(row.get("free_running", False)),
        )


def clip(text: str, limit: int = CLIP_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def render_history(trace: Trace, t: int) -> str:
    blocks = [f"### Step 0 (initial observation, before the first action)\nOBSERVATION: {clip(trace.observations[0])}"]
    for k in range(1, t + 1):
        blocks.append(f"### Step {k}\nACTION: {clip(trace.actions[k - 1])}\nOBSERVATION: {clip(trace.observations[k])}")
    return "\n".join(blocks)


def spread(traces: list[Trace], limit: int | None) -> list[Trace]:
    if limit is None or limit <= 0 or limit >= len(traces):
        return traces
    return [traces[index * len(traces) // limit] for index in range(limit)]


def read_jsonl(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_traces(path: str | Path) -> list[Trace]:
    if not Path(path).is_file():
        raise FileNotFoundError(f"no trace file at {path}")
    return [Trace.from_row(row) for row in read_jsonl(path)]
