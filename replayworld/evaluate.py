from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
from dataclasses import dataclass, field

from openai import APIError

from .config import Config, load_config, resolve
from .environments import load_environment
from .environments.common import EMPTY, OTHER
from .llm import LanguageModel, parse_json, preflight
from .prompts import load_prompt, prompt
from .repertoire import Repertoire
from .simulator import Simulator
from .traces import Trace, clip, load_traces, render_history, write_jsonl

JUDGED = ("Format", "Consistency", "Factuality")
CRITERIA = ("Format", "EnvReaction", "Consistency", "Factuality", "LongHorizon", "ActionPreserve")
MINIMUM_RATING = 1
JUDGE_RETRY_TOKENS = 65536
TASK_CHARS = 1500
ACTION_CHARS = 600
CANDIDATE_CHARS = 800
AGENT_HISTORY_CHARS = 2500
AGENT_OBSERVATION_CHARS = 4000
EQUIVALENCE_HISTORY_CHARS = 6000
JSON_OBJECT = re.compile(r"\{.*\}", re.S)


@dataclass
class Scored:
    trace_id: str
    t: int
    prediction: str
    recorded: str
    ratings: dict[str, int | None] = field(default_factory=dict)
    predicted_type: str = ""
    recorded_type: str = ""
    actions: dict[str, str] = field(default_factory=dict)
    preserved: bool | None = None
    long_horizon: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.trace_id,
            "t": self.t,
            "prediction": self.prediction,
            "recorded": self.recorded,
            "ratings": self.ratings,
            "predicted_type": self.predicted_type,
            "recorded_type": self.recorded_type,
            "actions": self.actions,
            "preserved": self.preserved,
            "LongHorizon": self.long_horizon,
        }


def rescale(rating: int | None) -> float | None:
    return None if rating is None else 100.0 * (rating - 1) / 4.0


def parse_rating(text: str, key: str) -> int | None:
    match = JSON_OBJECT.search(text or "")
    if match:
        try:
            value = json.loads(match.group(0)).get(key)
            if type(value) is int and 1 <= value <= 5:
                return value
        except json.JSONDecodeError:
            pass
    fallback = re.search(rf'"{key}"\s*:\s*([1-5])\b', text or "")
    return int(fallback.group(1)) if fallback else None


class Judge:
    def __init__(self, model: LanguageModel, environment: str):
        self.model = model
        self.notes = load_prompt(f"{environment}/factuality_notes")

    def messages(self, criterion: str, trace: Trace, t: int, prediction: str) -> list[dict]:
        user = prompt(
            f"judges/{criterion.lower()}_user",
            task=clip(trace.task),
            steps=render_history(trace, t),
            action_t=clip(trace.actions[t]),
            gt=clip(trace.recorded(t)),
            gt_truncated_note="\n" + load_prompt("judges/clipped_note") if trace.clipped else "",
            prediction=clip(prediction),
            environment_notes=self.notes,
        )
        return [
            {"role": "system", "content": load_prompt(f"judges/{criterion.lower()}_system")},
            {"role": "user", "content": user},
        ]

    async def rate(self, criterion: str, trace: Trace, t: int, prediction: str) -> int | None:
        if not prediction.strip():
            return MINIMUM_RATING
        messages = self.messages(criterion, trace, t, prediction)
        for budget in (None, JUDGE_RETRY_TOKENS):
            reply = await self.model.reply(messages, max_tokens=budget, thinking=None)
            rating = parse_rating(reply.text, criterion.lower())
            if rating is not None:
                return rating
        return None


def normalize_action(action: str) -> str:
    text = (action or "").strip()
    if "Action:" in text:
        tail = text.split("Action:", 1)[1]
        text = "Action:" + "\n".join(tail.strip().splitlines()[:2])
    else:
        text = text.splitlines()[0] if text else ""
    text = re.sub(r"\s+", " ", text.strip().strip("`").strip())
    return text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'").lower()


class ActionPreserve:
    def __init__(self, agent: LanguageModel, judge: LanguageModel):
        self.agent = agent
        self.judge = judge

    @staticmethod
    def history(trace: Trace, t: int, observation_chars: int) -> str:
        return "\n".join(
            f"[observation {k}]\n{clip(trace.observations[k], observation_chars)}\n"
            f"[action {k}]\n{clip(trace.actions[k], ACTION_CHARS)}"
            for k in range(t + 1)
        )

    async def next_action(self, trace: Trace, t: int, observation: str) -> str:
        user = prompt(
            "judges/action_preserve_agent_user",
            task=clip(trace.task, TASK_CHARS),
            history=self.history(trace, t, AGENT_HISTORY_CHARS),
            previous=t,
            observation=clip(observation, AGENT_OBSERVATION_CHARS),
        )
        messages = [
            {"role": "system", "content": load_prompt("judges/action_preserve_agent_system")},
            {"role": "user", "content": user},
        ]
        return (await self.agent.reply(messages, temperature=0.0, thinking=False)).text

    async def equivalent(self, trace: Trace, t: int, action_a: str, action_b: str) -> bool:
        user = prompt(
            "judges/action_preserve_equivalence_user",
            task=clip(trace.task, TASK_CHARS),
            history=self.history(trace, t, EQUIVALENCE_HISTORY_CHARS),
            action_a=clip(action_a, CANDIDATE_CHARS),
            action_b=clip(action_b, CANDIDATE_CHARS),
        )
        messages = [
            {"role": "system", "content": load_prompt("judges/action_preserve_equivalence_system")},
            {"role": "user", "content": user},
        ]
        reply = await self.judge.reply(messages, temperature=0.0, thinking=None)
        return (parse_json(reply.text) or {}).get("equivalent") is True

    async def preserved(self, trace: Trace, t: int, action_a: str, action_b: str) -> bool:
        if not action_a.strip() or not action_b.strip():
            return False
        if normalize_action(action_a) == normalize_action(action_b):
            return True
        return await self.equivalent(trace, t, action_a, action_b)


def env_reaction(pairs: list[tuple[str, str]]) -> float | None:
    recalls: dict[str, list[int]] = {}
    for recorded, predicted in pairs:
        if recorded in (EMPTY, OTHER):
            continue
        recalls.setdefault(recorded, [0, 0])
        recalls[recorded][1] += 1
        recalls[recorded][0] += recorded == predicted
    k = len(recalls)
    if k < 2:
        return None
    balanced = statistics.mean(hit / total for hit, total in recalls.values())
    return max(0.0, 100.0 * (balanced - 1.0 / k) / (1.0 - 1.0 / k))


def mean(values: list[float | None]) -> float | None:
    kept = [value for value in values if value is not None]
    return statistics.mean(kept) if kept else None


async def evaluate(
    config: Config,
    traces_path: str,
    repertoire_path: str,
    model: LanguageModel | None = None,
    judge_model: LanguageModel | None = None,
    agent: LanguageModel | None = None,
    action_preserve_judge: LanguageModel | None = None,
) -> dict:
    environment = load_environment(config)
    model = model or LanguageModel(config.simulator)
    simulator = Simulator(model, environment, config.harness)
    await simulator.preflight()
    judge = Judge(judge_model or LanguageModel(config.judge), environment.name)
    action_preserve = ActionPreserve(
        agent or LanguageModel(config.agent), action_preserve_judge or LanguageModel(config.action_preserve_judge)
    )
    await preflight(judge.model, "judge")
    await preflight(action_preserve.agent, "agent", thinking=False)
    await preflight(action_preserve.judge, "action-equivalence judge")
    repertoire = Repertoire.load(resolve(repertoire_path))
    traces = load_traces(resolve(traces_path))
    on_recorded: dict[str, str] = {}

    async def predict(trace: Trace, t: int, fresh_sandbox: bool = True) -> str:
        prediction = await simulator.predict(
            trace,
            t,
            repertoire,
            capabilities=config.harness.capabilities,
            exemplar=True,
            fresh_sandbox=fresh_sandbox,
            thinking=True,
            temperature=0.0,
            max_tokens=config.harness.simulation_max_tokens,
        )
        return prediction.text

    async def score(trace: Trace) -> Scored:
        t = trace.length - 1
        prediction = await predict(trace, t)
        row = Scored(trace.trace_id, t, prediction, trace.recorded(t))
        criteria = [criterion for criterion in JUDGED if criterion != "Consistency" or t > 0]
        ratings = await asyncio.gather(*[judge.rate(criterion, trace, t, prediction) for criterion in criteria])
        row.ratings = dict(zip(criteria, ratings))
        row.predicted_type = environment.response_type(prediction, trace.observations[t])
        row.recorded_type = environment.response_type(row.recorded, trace.observations[t])
        if not trace.final:
            on_predicted = await action_preserve.next_action(trace, t, prediction) if prediction.strip() else ""
            row.actions = {"on_recorded": on_recorded[trace.trace_id], "on_predicted": on_predicted}
            row.preserved = await action_preserve.preserved(trace, t, on_predicted, on_recorded[trace.trace_id])
        return row

    async def recorded_action(trace: Trace) -> None:
        if not trace.final:
            on_recorded[trace.trace_id] = await action_preserve.next_action(
                trace, trace.length - 1, trace.recorded(trace.length - 1)
            )

    async def ceiling(trace: Trace) -> bool | None:
        if trace.final:
            return None
        t = trace.length - 1
        again = await action_preserve.next_action(trace, t, trace.recorded(t))
        return await action_preserve.preserved(trace, t, again, on_recorded[trace.trace_id])

    async def long_horizon(trace: Trace) -> float | None:
        if not trace.free_running:
            return None
        simulated = list(trace.observations)
        for k in range(trace.length):
            running = Trace(trace.trace_id, trace.task, simulated, trace.actions, trace.reward)
            simulated[k + 1] = await predict(running, k, fresh_sandbox=k == 0)
        t = trace.length - 1
        ratings = await asyncio.gather(
            *[judge.rate(criterion, trace, t, simulated[trace.length]) for criterion in ("Consistency", "Factuality")]
        )
        values = [rescale(rating) for rating in ratings]
        return None if any(value is None for value in values) else statistics.mean(values)

    await asyncio.gather(*[recorded_action(trace) for trace in traces])
    rows = await asyncio.gather(*[score(trace) for trace in traces])
    ceilings = await asyncio.gather(*[ceiling(trace) for trace in traces])
    horizons = await asyncio.gather(*[long_horizon(trace) for trace in traces])
    for row, horizon in zip(rows, horizons):
        row.long_horizon = horizon

    judged = {criterion: [rescale(row.ratings.get(criterion)) for row in rows] for criterion in JUDGED}
    types = [(row.recorded_type, row.predicted_type) for row in rows]
    preserved = [float(row.preserved) for row in rows if row.preserved is not None]
    ceiling_rate = mean([float(value) for value in ceilings if value is not None])
    rate = mean(preserved)
    scores = {
        "Format": mean(judged["Format"]),
        "EnvReaction": env_reaction(types),
        "Consistency": mean(judged["Consistency"]),
        "Factuality": mean(judged["Factuality"]),
        "LongHorizon": mean(horizons),
        "ActionPreserve": None if rate is None or not ceiling_rate else min(100.0, 100.0 * rate / ceiling_rate),
    }
    coverage = {
        "Format": sum(value is not None for value in judged["Format"]),
        "EnvReaction": sum(recorded not in (EMPTY, OTHER) for recorded, _ in types),
        "Consistency": sum(value is not None for value in judged["Consistency"]),
        "Factuality": sum(value is not None for value in judged["Factuality"]),
        "LongHorizon": sum(value is not None for value in horizons),
        "ActionPreserve": len(preserved),
    }
    report = {
        "traces": len(rows),
        "scores": scores,
        "coverage": coverage,
        "action_preserve_rate": None if rate is None else 100.0 * rate,
        "action_preserve_ceiling": None if ceiling_rate is None else 100.0 * ceiling_rate,
    }
    write_jsonl(config.output("evaluate", "predictions.jsonl"), [row.to_dict() for row in rows])
    config.output("evaluate", "scores.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Rate the simulator on test traces with the six ReplayBench criteria.")
    parser.add_argument("--config", default="configs/webshop.yaml")
    parser.add_argument("--traces", default=None)
    parser.add_argument("--repertoire", default=None)
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    traces = arguments.traces or config.data.test_traces
    repertoire = arguments.repertoire or config.repertoire.selected
    try:
        report = asyncio.run(evaluate(config, traces, repertoire))
    except APIError as error:
        raise SystemExit(f"a request failed: {error}") from None
    for name in CRITERIA:
        value = report["scores"][name]
        print(f"{name:>14}: {'-' if value is None else f'{value:.1f}'}  ({report['coverage'][name]} traces)")


if __name__ == "__main__":
    main()
