from __future__ import annotations

import re

from .common import Environment, decoded, is_present

ERROR_TEXT = re.compile(r"\bError\b|Exception|Traceback")
ERROR_KEY = re.compile(r'"error"\s*:\s*"[^"]')
VALUE = "value"
ERROR = "error"


def failed(element) -> bool:
    if isinstance(element, str):
        return bool(ERROR_TEXT.search(element) or ERROR_KEY.search(element))
    if isinstance(element, dict):
        if is_present(element.get("error")):
            return True
        return any(item is False for key, item in element.items() if key.endswith("status") or key == "success")
    return False


class BFCL(Environment):
    name = "bfcl"

    def classify(self, text: str, previous: str) -> str:
        value = decoded(text)
        elements = value if isinstance(value, list) else [value]
        return ERROR if any(failed(element) for element in elements) else VALUE
