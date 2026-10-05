from __future__ import annotations

import argparse
import random
from collections import defaultdict

from replayworld.config import load_config, resolve
from replayworld.traces import read_jsonl, write_jsonl

MIN_STEPS = 2
FAILED_REQUEST = ("timed out", "connectionpool", "maximum request limit", "connection refused")


def is_valid(row: dict) -> bool:
    if not row.get("task", "").strip() or len(row.get("steps", [])) < MIN_STEPS:
        return False
    observations = [row.get("initial_observation") or ""] + [step["observation"] for step in row["steps"]]
    return not any(marker in observation.lower() for observation in observations for marker in FAILED_REQUEST)


def split(rows: list[dict], arbitration_share: float, seed: int) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    by_source: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_source[row.get("source", "")].append(row)
    replay, arbitration = [], []
    for source in sorted(by_source):
        traces = by_source[source]
        rng.shuffle(traces)
        count = round(len(traces) * arbitration_share)
        arbitration += traces[:count]
        replay += traces[count:]
    rng.shuffle(replay)
    rng.shuffle(arbitration)
    return replay, arbitration


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge collected traces and split them into replay and arbitration traces."
    )
    parser.add_argument("--config", default="configs/webshop.yaml")
    parser.add_argument("--traces", nargs="+", required=True)
    parser.add_argument("--arbitration_share", type=float, default=0.111)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    options = parser.parse_args()
    config = load_config(options.config)
    targets = [resolve(config.data.replay_traces), resolve(config.data.arbitration_traces)]
    if not options.overwrite and any(target.exists() for target in targets):
        parser.error("the trace files of this config already exist; pass --overwrite to replace them")
    rows = [row for path in options.traces for row in read_jsonl(resolve(path)) if is_valid(row)]
    replay, arbitration = split(rows, options.arbitration_share, options.seed)
    write_jsonl(targets[0], replay)
    write_jsonl(targets[1], arbitration)
    print(f"replay traces: {len(replay)}, arbitration traces: {len(arbitration)}")


if __name__ == "__main__":
    main()
