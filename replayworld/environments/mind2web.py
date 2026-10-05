from __future__ import annotations

import re

from .common import OTHER, Environment, jaccard

URL = re.compile(r"url='([^']*)'")
DIALOG = re.compile(r"(?m)^\s*(?:\[[^\]]*\]\s+)?(?:alert)?dialog\b")
NO_CHANGE = "no_change"
CHANGED = "changed"
SAME_PAGE_OVERLAP = 0.5


def root_url(page: str) -> str | None:
    for line in page.split("\n"):
        if line.strip():
            match = URL.search(line)
            return match.group(1).strip().rstrip("/") if match else None
    return None


class Mind2Web(Environment):
    name = "mind2web"

    def classify(self, text: str, previous: str) -> str:
        if "RootWebArea" not in text[:200]:
            return OTHER
        url = root_url(text)
        if url is None:
            return OTHER
        if url != root_url(previous):
            return CHANGED
        if len(DIALOG.findall(text)) > len(DIALOG.findall(previous)):
            return CHANGED
        return NO_CHANGE if jaccard(text, previous) >= SAME_PAGE_OVERLAP else CHANGED
