from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from replayworld.config import resolve
from replayworld.traces import write_jsonl


def load_queries(path: str | Path, limit: int | None = None) -> list[str]:
    queries = []
    with open(resolve(path), encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                queries.append(json.loads(line)["query"])
    return queries[:limit] if limit else queries


def trace_row(
    source: str,
    index: int,
    task: str,
    initial_observation: str,
    steps: list[dict],
    reward: float,
    clipped: bool = False,
) -> dict:
    row = {
        "id": f"{source}-{index:05d}",
        "source": source,
        "task": task,
        "initial_observation": initial_observation,
        "steps": steps,
        "reward": reward,
    }
    return {**row, "clipped": True} if clipped else row


def subset(count: int, sample: int | None, seed: int) -> list[int]:
    if not sample or sample >= count:
        return list(range(count))
    return sorted(random.Random(seed).sample(range(count), sample))


def save(path: str | Path, rows: list[dict | None]) -> int:
    kept = [row for row in rows if row and row["steps"]]
    write_jsonl(resolve(path), kept)
    return len(kept)


def arguments(description: str, queries: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--output", required=True)
    if queries:
        parser.add_argument("--config", default="configs/webshop.yaml")
        parser.add_argument("--queries", required=True)
        parser.add_argument("--limit", type=int, default=None)
    else:
        parser.add_argument("--sample", type=int, default=None)
        parser.add_argument("--seed", type=int, default=42)
    return parser
