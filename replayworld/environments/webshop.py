from __future__ import annotations

import re

from .common import OTHER, UNPARSED, Environment, decoded, is_present, literal

ASIN = re.compile(r"\b[Bb]0[0-9A-Za-z]{8}\b")
PRODUCT_ID = re.compile(r'"(?:product_id|shop_id|asin)"\s*:\s*"?([\w-]+)"?')
ASIN_ROW = re.compile(r"\[SEP\] B0[A-Z0-9]{8} \[SEP\]")
RESULT_COUNT = re.compile(r"Page \d+ \(Total results: \d+\)")
PRICE = re.compile(r"\[SEP\] Price: \$")
PAGE_ERROR = re.compile(
    r"Product Not Found|Invalid [Aa]ction|(?:^|\n|\[SEP\] )\s*Error:|not a valid clickable|not clickable"
)
ERROR_KEY = re.compile(r'"error"\s*:\s*"((?:[^"\\]|\\.)*)"')
ERROR_MESSAGE = re.compile(r"invalid|not found|unauthori[sz]ed|forbidden|\berror\b", re.I)
FAILED_STATUS = ("error", "fail", "failed", "failure")

RESULTS_PAGE = "results_page"
PRODUCT_PAGE = "product_page"
RECEIPT = "receipt"
OTHER_PAGE = "other_page"
RESULT = "result"
EMPTY_RESULT_OR_ERROR = "empty_result_or_error"


def is_empty_payload(payload) -> bool:
    if payload is None:
        return True
    if isinstance(payload, str):
        return payload.strip() in ("", "None", "null", "[]", "{}")
    if isinstance(payload, dict):
        return len(payload) == 0 or all(is_empty_payload(item) for item in payload.values())
    if isinstance(payload, list):
        return len(payload) == 0
    return False


def is_error_payload(payload) -> bool:
    if isinstance(payload, dict):
        if is_present(payload.get("error")) or payload.get("status") is False:
            return True
        return any(
            isinstance(payload.get(key), str) and ERROR_MESSAGE.search(payload[key])
            for key in ("message", "msg", "detail")
        )
    if isinstance(payload, str):
        return bool(re.match(r"^\s*(?:Invalid|Error)\b", payload))
    return False


def api_response_type(value) -> str:
    if isinstance(value, dict):
        if is_present(value.get("error")) or str(value.get("status", "")).lower() in FAILED_STATUS:
            return EMPTY_RESULT_OR_ERROR
        if "error" in value and "response" in value:
            payload = decoded(value.get("response"))
            return EMPTY_RESULT_OR_ERROR if is_error_payload(payload) or is_empty_payload(payload) else RESULT
        return EMPTY_RESULT_OR_ERROR if is_empty_payload(value) else RESULT
    if isinstance(value, list):
        failed = all(isinstance(item, dict) and is_present(item.get("error")) for item in value)
        return EMPTY_RESULT_OR_ERROR if not value or failed else RESULT
    return RESULT


class WebShop(Environment):
    name = "webshop"
    skill_prefixes = ("cnt_",)

    def classify(self, text: str, previous: str) -> str:
        if "Thank you for shopping" in text or "Your score" in text:
            return RECEIPT
        if "[SEP]" in text:
            if PAGE_ERROR.search(text):
                return EMPTY_RESULT_OR_ERROR
            if RESULT_COUNT.search(text) or len(ASIN_ROW.findall(text)) >= 2:
                return RESULTS_PAGE
            if "[SEP] Buy Now" in text or PRICE.search(text) or "[SEP] < Prev" in text:
                return PRODUCT_PAGE
            return OTHER_PAGE
        if text[0] in "{[":
            value = literal(text)
            if value is UNPARSED or value is None:
                failed = ERROR_KEY.search(text[:400])
                return EMPTY_RESULT_OR_ERROR if failed and failed.group(1).strip() else RESULT
            return api_response_type(value)
        return OTHER

    def identifiers(self, observation: str) -> set[str]:
        return {asin.upper() for asin in ASIN.findall(observation)} | set(PRODUCT_ID.findall(observation))
