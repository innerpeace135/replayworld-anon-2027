from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

from .repertoire import Repertoire
from .replay import replay
from .roles import Aggregator, Comparator, DiscrepancySummary
from .simulator import Prediction
from .traces import Trace

SHARE_WEIGHT = 50.0
QUALITY_WEIGHT = 25.0
CAUSE_WEIGHT = 25.0
CAUSE_SCALE = 10


@dataclass
class ArbitrationScore:
    cycle: int
    rule_check_score: float
    discrepancy_score: float
    discrepancies: int

    @property
    def arbitration_score(self) -> float:
        return 0.5 * (self.rule_check_score + self.discrepancy_score)

    def to_dict(self) -> dict:
        return {**asdict(self), "arbitration_score": self.arbitration_score}


class Arbiter:
    def __init__(self, environment):
        self.environment = environment

    def rule_check_score(self, predictions: list[Prediction], traces: list[Trace], steps: list[int]) -> float:
        scores = []
        for prediction, trace, t in zip(predictions, traces, steps):
            recorded, previous = trace.recorded(t), trace.observations[t]
            checks = self.environment.rule_checks(prediction.text, recorded, previous) if prediction.parsed else [0.0]
            scores.append(sum(checks) / len(checks))
        return 100.0 * sum(scores) / len(scores)

    def discrepancy_score(self, summary: DiscrepancySummary) -> float:
        shares = list(summary.causes.values())
        mean_share = sum(shares) / len(shares) if shares else 0.0
        quality = summary.n_quality / max(summary.n_discrepancies, 1)
        few_causes = max(0.0, (CAUSE_SCALE - len(shares)) / CAUSE_SCALE)
        return SHARE_WEIGHT * (1.0 - mean_share) + QUALITY_WEIGHT * quality + CAUSE_WEIGHT * few_causes


class MCCA:
    def __init__(
        self,
        simulator,
        comparator: Comparator,
        aggregator: Aggregator,
        arbiter: Arbiter,
        arbitration_traces: list[Trace],
        sample_size: int,
        patience: int,
        seed: int,
        thinking: bool = False,
    ):
        self.simulator = simulator
        self.comparator = comparator
        self.aggregator = aggregator
        self.arbiter = arbiter
        self.arbitration_traces = arbitration_traces
        self.sample_size = sample_size
        self.patience = patience
        self.seed = seed
        self.thinking = thinking
        self.best = -math.inf
        self.winner = 0
        self.cycles_without_improvement = 0
        self.history: list[dict] = []

    async def arbitrate(self, repertoire: Repertoire, cycle: int) -> float:
        rng = random.Random(self.seed + cycle)
        sample = rng.sample(self.arbitration_traces, min(self.sample_size, len(self.arbitration_traces)))
        steps = [rng.randrange(trace.length) for trace in sample]
        predictions, discrepancies = await replay(
            self.simulator, self.comparator, repertoire, sample, steps, self.thinking
        )
        summary = await self.aggregator.aggregate(discrepancies, cycle)
        if not summary.parsed:
            self.history.append({"cycle": cycle, "arbitration_score": None, "discrepancies": len(discrepancies)})
            return -math.inf
        score = ArbitrationScore(
            cycle,
            self.arbiter.rule_check_score(predictions, sample, steps),
            self.arbiter.discrepancy_score(summary),
            len(discrepancies),
        )
        self.history.append(score.to_dict())
        return score.arbitration_score

    def select(self, cycle: int, score: float) -> bool:
        if score > self.best:
            self.best = score
            self.winner = cycle
            self.cycles_without_improvement = 0
        else:
            self.cycles_without_improvement += 1
        return self.cycles_without_improvement >= self.patience
