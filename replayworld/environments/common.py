from __future__ import annotations

import ast
import json
import re

JSON_KEY = re.compile(r'"(\w+)"\s*:')
WORD = re.compile(r"[a-z0-9]+")
TOKEN = re.compile(r"\w+")
WRAPPER = "predicted_observation|tool_response|observation|output|result|response"
OPEN_TAG = re.compile(rf"^\s*<(?:{WRAPPER})>\s*", re.I)
CLOSE_TAG = re.compile(rf"\s*</(?:{WRAPPER})>?\s*$", re.I)
FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*\n?|\n?\s*```\s*$")
LABEL = re.compile(r"^\s*Observation:\s*", re.I)
AGENT_ARTIFACTS = ("<answer>", "<tool_call>", "<tools>", "Thought:", "### Step", "Action:")

EMPTY = "empty"
OTHER = "other"
UNPARSED = object()


def literal(text: str):
    for loader in (json.loads, ast.literal_eval):
        try:
            return loader(text)
        except (ValueError, SyntaxError, TypeError, RecursionError, MemoryError):
            continue
    return UNPARSED


def decoded(value, depth: int = 0):
    if isinstance(value, str) and depth < 4:
        text = value.strip()
        if text:
            inner = literal(text)
            if inner is not UNPARSED and (not isinstance(inner, str) or inner != value):
                return decoded(inner, depth + 1)
        return value
    if isinstance(value, list):
        return [decoded(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return {key: decoded(item, depth + 1) for key, item in value.items()}
    return value


def is_present(value) -> bool:
    return value not in (None, "", False) and not (isinstance(value, (dict, list)) and len(value) == 0)


def clean(text: str) -> str:
    for _ in range(2):
        text = FENCE.sub("", text)
        text = OPEN_TAG.sub("", text)
        text = CLOSE_TAG.sub("", text)
        text = LABEL.sub("", text, count=1)
    return text.strip()


def jaccard(first: str, second: str) -> float:
    left, right = set(TOKEN.findall(first.lower())), set(TOKEN.findall(second.lower()))
    return len(left & right) / len(left | right) if left or right else 0.0


class Environment:
    name = ""
    skill_prefixes: tuple[str, ...] = ()

    def parses(self, observation: str) -> bool:
        text = observation.strip()
        return bool(text) and "```" not in text and not text.startswith(AGENT_ARTIFACTS)

    def response_type(self, observation: str, previous: str = "") -> str:
        if not observation.strip():
            return EMPTY
        text = clean(observation)
        if not text or text.startswith(AGENT_ARTIFACTS):
            return OTHER
        return self.classify(text, previous)

    def classify(self, text: str, previous: str) -> str:
        raise NotImplementedError

    def identifiers(self, observation: str) -> set[str]:
        return set()

    def fields(self, observation: str) -> set[str]:
        return set(JSON_KEY.findall(observation)) or set(WORD.findall(observation.lower()))

    def rule_checks(self, prediction: str, recorded: str, previous: str = "") -> list[float]:
        checks = []
        identifiers = self.identifiers(recorded)
        if identifiers:
            checks.append(len(identifiers & self.identifiers(prediction)) / len(identifiers))
        fields = self.fields(recorded)
        if fields:
            checks.append(len(fields & self.fields(prediction)) / len(fields))
        predicted_type = self.response_type(prediction, previous)
        same_type = predicted_type == self.response_type(recorded, previous)
        checks.append(float(same_type and predicted_type not in (EMPTY, OTHER)))
        return checks
