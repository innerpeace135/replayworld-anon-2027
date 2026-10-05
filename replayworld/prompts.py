from __future__ import annotations

import re
from functools import cache

from .config import ROOT

SLOT = re.compile(r"\{\{(\w+)\}\}")


@cache
def load_prompt(name: str) -> str:
    return (ROOT / "prompts" / f"{name}.txt").read_text(encoding="utf-8").strip()


def has_prompt(name: str) -> bool:
    return (ROOT / "prompts" / f"{name}.txt").is_file()


def fill(template: str, **slots) -> str:
    return SLOT.sub(lambda match: str(slots[match.group(1)]), template)


def prompt(name: str, **slots) -> str:
    return fill(load_prompt(name), **slots)
