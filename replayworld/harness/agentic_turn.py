from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..llm import LanguageModel
from ..prompts import load_prompt
from .tools import ToolExecutor

PREDICTED_OBSERVATION = re.compile(r"<predicted_observation>(.*?)</predicted_observation>", re.S)


@dataclass
class Turn:
    prediction: str
    replies: int
    tool_calls: list[str] = field(default_factory=list)


def extract_observation(reply: str) -> str:
    block = PREDICTED_OBSERVATION.search(reply)
    return (block.group(1) if block else reply).strip()


async def agentic_turn(
    model: LanguageModel,
    context: list[dict],
    executor: ToolExecutor | None,
    reply_cap: int,
    **decoding,
) -> Turn:
    context = list(context)
    tool_calls: list[str] = []
    tools = executor.definitions if executor and executor.definitions else None
    for replies in range(1, reply_cap + 1):
        last = replies == reply_cap
        if last and tool_calls:
            context.append({"role": "user", "content": load_prompt("simulator/tools_disabled")})
        reply = await model.reply(context, tools=None if last else tools, **decoding)
        if last or not reply.tool_calls:
            break
        context.append(reply.message())
        for call in reply.tool_calls:
            result = await executor.execute(call.name, call.arguments)
            context.append({"role": "tool", "tool_call_id": call.call_id, "content": result})
            tool_calls.append(call.name)
    return Turn(extract_observation(reply.text), replies, tool_calls)
