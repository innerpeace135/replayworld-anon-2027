from __future__ import annotations

import re

from .common import Environment

INVALID_NOUN = (
    r"action|command|input|argument|option|syntax|format|operation|request|parameter|value|app|target(?:[ _]app)?"
    r"|choice|selection|index|type|path|file(?:name)?"
)
ERROR_OPENING = re.compile(
    r"^\s*(?:Error\b|Command failed|Failed to\b|Traceback|Cannot\b|Unable\b|Could ?n[o']t\b|Invalid (?:"
    + INVALID_NOUN
    + r")s?\b|Unknown (?:command|app|action)|SyntaxError|\w+Error:|[\w./-]+: (?:cannot|No such|command not found))",
    re.I,
)
ERROR_PHRASE = re.compile(
    r"does not exist|already exists|\bnot found\b|No such file|Permission denied|not available|not installed"
    r"|not supported|No module named|syntax error|is not a valid|binary file|command not found",
    re.I,
)
CONFIRMATION = re.compile(r"^\s*(?:Task finished|Successfully\b)", re.I)
NOTHING_FOUND = re.compile(r"^\s*No (?:\w+ ){1,3}found\b", re.I)
CONTENT = "content"
CONFIRM = "confirm"
NOTHING = "nothing"
ERROR = "error"


class OfficeBench(Environment):
    name = "officebench"

    def classify(self, text: str, previous: str) -> str:
        if NOTHING_FOUND.match(text):
            return NOTHING
        opening = "\n".join(text.split("\n")[:2])
        if ERROR_OPENING.match(text) or ERROR_PHRASE.search(opening):
            return ERROR
        return CONFIRM if CONFIRMATION.match(text) else CONTENT
