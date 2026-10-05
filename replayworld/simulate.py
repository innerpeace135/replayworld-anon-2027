from __future__ import annotations

import argparse
import asyncio
import random

from openai import APIError

from .config import Config, load_config, resolve
from .environments import load_environment
from .llm import LanguageModel
from .repertoire import Repertoire
from .simulator import Simulator
from .traces import load_traces, spread, write_jsonl


async def simulate(
    config: Config,
    traces_path: str,
    repertoire_path: str,
    limit: int,
    exemplar: bool,
    seed: int,
    model: LanguageModel | None = None,
) -> list[dict]:
    environment = load_environment(config)
    model = model or LanguageModel(config.simulator)
    simulator = Simulator(model, environment, config.harness)
    await simulator.preflight()
    repertoire = Repertoire.load(resolve(repertoire_path))
    traces = spread(load_traces(resolve(traces_path)), limit)
    rng = random.Random(seed)
    steps = [rng.randrange(trace.length) for trace in traces]
    predictions = await asyncio.gather(
        *[
            simulator.predict(
                trace,
                t,
                repertoire,
                capabilities=config.harness.capabilities,
                exemplar=exemplar,
                thinking=True,
                temperature=0.0,
                max_tokens=config.harness.simulation_max_tokens,
            )
            for trace, t in zip(traces, steps)
        ]
    )
    rows = []
    for trace, t, prediction in zip(traces, steps, predictions):
        checks = environment.rule_checks(prediction.text, trace.recorded(t), trace.observations[t])
        rows.append(
            {
                "id": trace.trace_id,
                "t": t,
                "action": trace.actions[t],
                "prediction": prediction.text,
                "recorded": trace.recorded(t),
                "parsed": prediction.parsed,
                "replies": prediction.replies,
                "tool_calls": prediction.tool_calls,
                "rule_check_score": 100.0 * sum(checks) / len(checks),
            }
        )
    write_jsonl(config.output("simulate", "predictions.jsonl"), rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict next observations with a skill repertoire.")
    parser.add_argument("--config", default="configs/webshop.yaml")
    parser.add_argument("--traces", required=True)
    parser.add_argument("--repertoire", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--exemplar", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    repertoire = arguments.repertoire or config.repertoire.selected
    try:
        rows = asyncio.run(
            simulate(config, arguments.traces, repertoire, arguments.limit, arguments.exemplar, arguments.seed)
        )
    except APIError as error:
        raise SystemExit(f"a request failed: {error}") from None
    parsed = sum(row["parsed"] for row in rows)
    score = sum(row["rule_check_score"] for row in rows) / max(len(rows), 1)
    print(f"predicted {len(rows)} steps, {parsed} parsed, rule check score {score:.1f}")


if __name__ == "__main__":
    main()
