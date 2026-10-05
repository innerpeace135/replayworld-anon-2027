from __future__ import annotations

import re

from .common import Environment, decoded, is_present

FAILURE_MESSAGE = re.compile(
    r"\bError\b|Exception|\bnot found\b|\bcannot\b|\bfail(?:ed|ure)?\b|\binvalid\b|\bunable\b"
    r"|please (?:log ?in|login|turn on|switch)|need to log ?in|not logged in|\bno \w+ found\b|\binsufficient\b"
    r"|\bunknown\b|does not exist|already exists",
    re.I,
)
FAILED_STATUS = ("error", "failed", "failure", "fail")
SUCCESS = "success"
FAILURE = "failure"


def failed(element) -> bool:
    if isinstance(element, str):
        return bool(FAILURE_MESSAGE.search(element))
    if not isinstance(element, dict):
        return False
    if "status" not in element:
        return is_present(element.get("error")) or any(
            isinstance(element.get(key), str) and FAILURE_MESSAGE.search(element[key]) for key in ("message", "msg")
        )
    status = element["status"]
    if status is False or (isinstance(status, str) and status.lower() in FAILED_STATUS):
        return True
    return is_present(element.get("error"))


class ACEBench(Environment):
    name = "acebench"

    def classify(self, text: str, previous: str) -> str:
        value = decoded(text)
        elements = value if isinstance(value, list) else [value]
        return FAILURE if any(failed(element) for element in elements) else SUCCESS
