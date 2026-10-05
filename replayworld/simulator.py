from __future__ import annotations

import hashlib
import shutil
import tempfile
import weakref
from dataclasses import dataclass, field
from pathlib import Path

from .config import HarnessConfig, resolve
from .harness.agentic_turn import agentic_turn
from .harness.tools import CODING, SHELL_TOOL_CALLS, ToolExecutor, shell_tool_group, skill_tools
from .llm import LanguageModel, preflight
from .prompts import has_prompt, load_prompt, prompt
from .repertoire import Repertoire
from .traces import Trace


@dataclass
class Prediction:
    text: str
    parsed: bool
    replies: int = 0
    tool_calls: list[str] = field(default_factory=list)


def history_messages(trace: Trace, t: int) -> list[dict]:
    first = prompt("simulator/first_step", observation=trace.observations[0], action=trace.actions[0])
    messages = [{"role": "user", "content": first}]
    for step in range(1, t + 1):
        messages.append({"role": "assistant", "content": trace.observations[step]})
        messages.append({"role": "user", "content": prompt("simulator/next_step", action=trace.actions[step])})
    return messages


def read(path: str) -> str:
    return resolve(path).read_text(encoding="utf-8").strip() if path and resolve(path).is_file() else ""


class Simulator:
    def __init__(self, model: LanguageModel, environment, config: HarnessConfig):
        self.model = model
        self.environment = environment
        self.config = config
        self.sandboxes: Path | None = None
        self.exemplar = read(config.format_exemplar)
        self.shell_note = read(config.shell_note)
        unknown = set(config.capabilities + config.replay_capabilities) - {CODING}
        if unknown:
            raise ValueError(f"unknown harness capabilities: {sorted(unknown)}")

    async def preflight(self) -> None:
        await preflight(self.model, "simulator", ToolExecutor(skill_tools(Repertoire())).definitions, thinking=False)

    def sandbox(self, trace: Trace) -> Path:
        if self.sandboxes is None:
            self.sandboxes = Path(tempfile.mkdtemp(prefix="replayworld-"))
            weakref.finalize(self, shutil.rmtree, self.sandboxes, True)
        return self.sandboxes / hashlib.sha1(trace.trace_id.encode("utf-8")).hexdigest()[:12]

    def system(
        self, trace: Trace, repertoire: Repertoire, capabilities: tuple[str, ...], exemplar: bool, single_reply: bool
    ) -> str:
        parts = [load_prompt(f"{self.environment.name}/environment"), f"Task the agent is pursuing: {trace.task}"]
        if CODING in capabilities:
            parts.append(prompt("simulator/local_tools", calls=SHELL_TOOL_CALLS))
        if exemplar and self.exemplar:
            if has_prompt(f"{self.environment.name}/format_rules"):
                parts.append(load_prompt(f"{self.environment.name}/format_rules"))
            parts.append("## Format Reference\n" + self.exemplar)
        if single_reply and len(repertoire):
            parts.append(repertoire.bodies())
        elif len(repertoire):
            parts.append(prompt("simulator/skill_index", count=len(repertoire), index=repertoire.index()))
        return load_prompt("simulator/system") + "\n\n# Reference Skills\n\n" + "\n\n".join(parts)

    def tool_executor(
        self, trace: Trace, repertoire: Repertoire, capabilities: tuple[str, ...], fresh_sandbox: bool
    ) -> ToolExecutor:
        tools = skill_tools(repertoire) if len(repertoire) else []
        if CODING in capabilities:
            tools += shell_tool_group(self.sandbox(trace), self.shell_note, self.config.shell_timeout, fresh_sandbox)
        return ToolExecutor(tools)

    async def predict(
        self,
        trace: Trace,
        t: int,
        repertoire: Repertoire,
        capabilities: list[str] | None = None,
        exemplar: bool = False,
        single_reply: bool = False,
        fresh_sandbox: bool = True,
        thinking: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Prediction:
        if single_reply:
            capabilities, reply_cap, executor = (), 1, None
        else:
            capabilities = tuple(self.config.replay_capabilities if capabilities is None else capabilities)
            reply_cap = self.config.reply_cap_with_tool_group if CODING in capabilities else self.config.reply_cap
            executor = self.tool_executor(trace, repertoire, capabilities, fresh_sandbox)
        system = self.system(trace, repertoire, capabilities, exemplar, single_reply)
        context = [{"role": "system", "content": system}, *history_messages(trace, t)]
        turn = await agentic_turn(
            self.model, context, executor, reply_cap, temperature=temperature, max_tokens=max_tokens, thinking=thinking
        )
        return Prediction(turn.prediction, self.environment.parses(turn.prediction), turn.replies, turn.tool_calls)
