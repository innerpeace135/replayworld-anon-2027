from __future__ import annotations

import asyncio
import weakref

from .config import load_config, resolve
from .environments import load_environment
from .llm import LanguageModel
from .repertoire import Repertoire
from .simulator import Simulator
from .traces import Trace


class WorldModel:
    def __init__(self, config_path: str = "configs/webshop.yaml", model: LanguageModel | None = None):
        self.config = load_config(config_path)
        self.simulator = Simulator(
            model or LanguageModel(self.config.simulator), load_environment(self.config), self.config.harness
        )
        self.repertoire = Repertoire.load(resolve(self.config.repertoire.selected))
        self.loop = asyncio.new_event_loop()
        weakref.finalize(self, self.loop.close)

    async def predict(self, task: str, observations: list[str], actions: list[str], episode: str = "episode") -> str:
        trace = Trace(episode, task, [*observations, ""], actions)
        prediction = await self.simulator.predict(
            trace,
            len(actions) - 1,
            self.repertoire,
            capabilities=self.config.harness.capabilities,
            exemplar=True,
            fresh_sandbox=len(actions) == 1,
            thinking=True,
            temperature=0.0,
            max_tokens=self.config.harness.simulation_max_tokens,
        )
        return prediction.text

    def step(self, task: str, observations: list[str], actions: list[str], episode: str = "episode") -> str:
        return self.loop.run_until_complete(self.predict(task, observations, actions, episode))
