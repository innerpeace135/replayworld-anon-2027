from __future__ import annotations

import argparse
import asyncio
import json
import random
import shutil

from openai import APIError

from .config import Config, load_config, resolve
from .embedding import Embedder
from .environments import load_environment
from .llm import LanguageModel
from .lpf import lpf
from .mcca import MCCA, Arbiter
from .prompts import has_prompt
from .repertoire import Repertoire, Revision
from .replay import replay
from .roles import Aggregator, Comparator, DiscrepancySummary, Reviser
from .sbs import Clusters, sbs
from .simulator import Simulator
from .traces import load_traces, write_jsonl

ROLES = ("comparator", "aggregator", "reviser")


async def evolve(config: Config, model: LanguageModel | None = None, embedder=None) -> Repertoire:
    settings = config.evolve
    environment = load_environment(config)
    if not config.repertoire.initial:
        raise ValueError("repertoire.initial names the repertoire that the replay loop starts from")
    missing = [role for role in ROLES if not has_prompt(f"{environment.name}/{role}")]
    if missing:
        raise ValueError(f"prompts/{environment.name}/ has no {', '.join(missing)} prompt")
    repertoire = Repertoire.load(resolve(config.repertoire.initial))
    replay_traces = load_traces(resolve(config.data.replay_traces))
    arbitration_traces = load_traces(resolve(config.data.arbitration_traces))
    if not arbitration_traces:
        raise ValueError("MCCA needs arbitration traces")
    clusters = Clusters.load(config.output("clusters.json"))
    if clusters.trace_ids != [trace.trace_id for trace in replay_traces]:
        raise ValueError("clusters.json does not index the replay traces; run `python -m replayworld.sbs` first")

    model = model or LanguageModel(config.simulator)
    simulator = Simulator(model, environment, config.harness)
    await simulator.preflight()
    embedder = embedder or Embedder(config.embedding)
    comparator = Comparator(model, environment.name)
    aggregator = Aggregator(model, environment.name)
    reviser = Reviser(
        model,
        environment.name,
        settings.frequency_threshold,
        config.repertoire.skill_body_cap,
        settings.max_deletes_per_cycle,
        environment.skill_prefixes,
    )

    mcca = MCCA(
        simulator,
        comparator,
        aggregator,
        Arbiter(environment),
        arbitration_traces,
        settings.arbitration_sample,
        settings.patience,
        settings.seed,
        settings.replay_thinking,
    )
    rng = random.Random(settings.seed)
    selected = repertoire
    batched: set[int] = set()
    last = 0

    for cycle in range(1, settings.cycle_cap + 1):
        eligible = [index for index in range(len(replay_traces)) if index not in batched]
        if not eligible:
            break
        pre_sample = sbs(eligible, clusters, settings.n_pre, rng)
        retained = await lpf(
            simulator,
            repertoire,
            [replay_traces[index] for index in pre_sample],
            settings.n_sl,
            settings.n_step,
            embedder,
            rng,
            cold_start=cycle == 1,
        )
        batch = sbs([pre_sample[position] for position in retained], clusters, settings.batch_size, rng)
        batched.update(batch)

        traces = [replay_traces[index] for index in batch]
        steps = [rng.randrange(trace.length) for trace in traces]
        predictions, discrepancies = await replay(
            simulator, comparator, repertoire, traces, steps, settings.replay_thinking
        )
        parsed = sum(prediction.parsed for prediction in predictions)
        if discrepancies:
            summary = await aggregator.aggregate(discrepancies, cycle)
            replayed = [(trace.actions[t], trace.recorded(t)) for trace, t in zip(traces, steps)]
            revision = await reviser.revise(repertoire, summary, replayed)
        else:
            summary = DiscrepancySummary(cycle, 0, 0)
            revision = Revision(note="no discrepancy")

        repertoire = repertoire.apply(revision)
        if cycle % settings.consolidation_period == 0:
            repertoire = repertoire.consolidate(settings.consolidation_overlap, config.repertoire.skill_body_cap)

        score = await mcca.arbitrate(repertoire, cycle)
        stop = mcca.select(cycle, score)
        if mcca.winner == cycle:
            selected = repertoire

        folder = config.folder("evolve", f"cycle_{cycle:02d}")
        repertoire.save(folder / "repertoire")
        write_jsonl(folder / "discrepancies.jsonl", [item.to_dict() for item in discrepancies])
        report = {
            "cycle": cycle,
            "batch": [replay_traces[index].trace_id for index in batch],
            "parsed": parsed,
            "summary": summary.to_dict(),
            "revision": [edit.to_dict() for edit in revision.edits],
            "note": revision.note,
            "arbitration": mcca.history[-1],
            "skills": [skill.identifier for skill in repertoire],
        }
        (folder / "cycle.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"cycle {cycle}: {parsed}/{len(batch)} predictions parsed, {len(discrepancies)} discrepancies, "
            f"{len(revision.edits)} edits, {len(repertoire)} skills, arbitration score {score:.2f}"
        )
        last = cycle
        if stop:
            break

    for folder in config.folder("evolve").glob("cycle_[0-9][0-9]"):
        if int(folder.name[-2:]) > last:
            shutil.rmtree(folder)
    selected.save(config.folder("evolve") / "selected")
    outcome = {"winner": mcca.winner, "history": mcca.history}
    config.output("evolve", "arbitration.json").write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay-driven skill evolution.")
    parser.add_argument("--config", default="configs/webshop.yaml")
    arguments = parser.parse_args()
    try:
        selected = asyncio.run(evolve(load_config(arguments.config)))
    except APIError as error:
        raise SystemExit(f"a request failed: {error}") from None
    print(f"selected repertoire: {len(selected)} skills")


if __name__ == "__main__":
    main()
