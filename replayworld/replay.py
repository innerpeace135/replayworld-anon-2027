from __future__ import annotations

import asyncio

from .repertoire import Repertoire
from .roles import Comparator, Discrepancy
from .simulator import Prediction
from .traces import Trace


async def replay(
    simulator,
    comparator: Comparator,
    repertoire: Repertoire,
    traces: list[Trace],
    steps: list[int],
    thinking: bool = False,
) -> tuple[list[Prediction], list[Discrepancy]]:
    async def replay_step(trace: Trace, t: int) -> tuple[Prediction, Discrepancy | None]:
        prediction = await simulator.predict(trace, t, repertoire, thinking=thinking)
        if not prediction.parsed:
            return prediction, None
        return prediction, await comparator.compare(trace, t, prediction.text)

    replayed = await asyncio.gather(*[replay_step(trace, t) for trace, t in zip(traces, steps)])
    predictions = [prediction for prediction, _ in replayed]
    discrepancies = [discrepancy for _, discrepancy in replayed if discrepancy is not None]
    return predictions, discrepancies
