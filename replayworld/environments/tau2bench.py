from __future__ import annotations

import re

from .common import OTHER, Environment

USER_TAG = "[user]"
TOOL_TAG = "[tool]"
AGENT_MARKUP = re.compile(r"</?tool_call>|<function=|</function>|<parameter=|tool_calls=\[|</?skill>")
USER_OPENING = re.compile(
    r"^\s*(?:I\b|I'm|I'd|I've|I'll|My\b|We\b|Hi\b|Hello\b|Hey\b|Yes\b|Sure\b|Thanks|Thank you|Please\b|Can you"
    r"|Could you|Oh\b|Um\b|Actually\b|Sorry|Yeah|Alright|Let me|Hmm|Well\b|Of course|Absolutely)",
    re.I,
)
USER_TURN = "user_turn"
TOOL_RESULT = "tool_result"


class Tau2Bench(Environment):
    name = "tau2bench"

    def classify(self, text: str, previous: str) -> str:
        if text.startswith(USER_TAG):
            return USER_TURN
        if text.startswith(TOOL_TAG):
            return TOOL_RESULT
        if AGENT_MARKUP.search(text):
            return OTHER
        return USER_TURN if USER_OPENING.match(text) else TOOL_RESULT
