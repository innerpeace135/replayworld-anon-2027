from __future__ import annotations

import re

from .common import OTHER, Environment

HEADER = re.compile(r"status=(ok|error)\s*\|\s*output_exists=(True|False)", re.I)
OK_OUTPUT = "ok_output"
OK_NO_OUTPUT = "ok_no_output"
ERROR = "error"


class SheetCopilot(Environment):
    name = "sheetcopilot"

    def classify(self, text: str, previous: str) -> str:
        header = HEADER.search(text[:200])
        if not header:
            return OTHER
        if header.group(1).lower() == "error":
            return ERROR
        return OK_OUTPUT if header.group(2).lower() == "true" else OK_NO_OUTPUT
