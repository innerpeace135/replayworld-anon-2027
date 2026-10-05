from __future__ import annotations

import asyncio
import random

import numpy as np
from scipy.stats import rankdata

from .repertoire import Repertoire
from .traces import Trace

REWARD_BAND = (0.3, 0.9)
LENGTH_BAND = (50, 90)


def percentile_rank(values: np.ndarray) -> np.ndarray:
    return rankdata(values, method="average") / len(values)


def learnability(rewards: np.ndarray, max_errors: np.ndarray, mean_errors: np.ndarray) -> np.ndarray:
    return percentile_rank(rewards) * percentile_rank(max_errors) * (1.0 - percentile_rank(mean_errors))


def cold_start_ranking(traces: list[Trace]) -> np.ndarray:
    lengths = np.array([trace.length for trace in traces], dtype=np.float64)
    rewards = np.array([trace.reward for trace in traces], dtype=np.float64)
    low, high = np.percentile(lengths, LENGTH_BAND)
    rewarded = (rewards >= REWARD_BAND[0]) & (rewards <= REWARD_BAND[1])
    typical = (lengths >= low) & (lengths <= high)
    return rewarded.astype(np.float64) + typical.astype(np.float64)


def top(scores: np.ndarray, n: int, rng: random.Random) -> list[int]:
    order = [index for index in range(len(scores)) if np.isfinite(scores[index])]
    rng.shuffle(order)
    order.sort(key=lambda index: -scores[index])
    return order[:n]


async def replay_errors(
    simulator, repertoire: Repertoire, traces: list[Trace], n_step: int, embedder, rng: random.Random
):
    plan = [
        (index, t)
        for index, trace in enumerate(traces)
        for t in rng.sample(range(trace.length), min(n_step, trace.length))
    ]
    predictions = await asyncio.gather(
        *[simulator.predict(traces[index], t, repertoire, single_reply=True) for index, t in plan]
    )
    scored = [(index, t, prediction.text) for (index, t), prediction in zip(plan, predictions) if prediction.text]
    errors: dict[int, list[float]] = {}
    if scored:
        predicted = embedder.encode([text for _, _, text in scored])
        recorded = embedder.encode([traces[index].recorded(t) for index, t, _ in scored])
        for row, (index, _, _) in enumerate(scored):
            errors.setdefault(index, []).append(1.0 - float(np.dot(predicted[row], recorded[row])))
    max_errors = np.array([max(errors[i]) if i in errors else np.nan for i in range(len(traces))])
    mean_errors = np.array([float(np.mean(errors[i])) if i in errors else np.nan for i in range(len(traces))])
    return max_errors, mean_errors


async def lpf(
    simulator,
    repertoire: Repertoire,
    pre_sample: list[Trace],
    n_sl: int,
    n_step: int,
    embedder,
    rng: random.Random,
    cold_start: bool,
) -> list[int]:
    if cold_start:
        return top(cold_start_ranking(pre_sample), n_sl, rng)
    max_errors, mean_errors = await replay_errors(simulator, repertoire, pre_sample, n_step, embedder, rng)
    scored = np.flatnonzero(~np.isnan(max_errors))
    scores = np.full(len(pre_sample), -np.inf)
    if len(scored):
        rewards = np.array([pre_sample[index].reward for index in scored], dtype=np.float64)
        scores[scored] = learnability(rewards, max_errors[scored], mean_errors[scored])
    return top(scores, n_sl, rng)
