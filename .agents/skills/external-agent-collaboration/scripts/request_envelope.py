"""Structured request fields consumed before natural-language classification."""

from __future__ import annotations

import json
from typing import Any


TASK_TYPES = {"code", "document", "research", "creative", "planning", "data", "file_operations", "personal_advice", "current_information"}
MODES = {"analyze", "draft", "critique", "revise", "execute", "verify"}


class RequestEnvelopeError(ValueError):
    pass


def parse(value: str) -> tuple[dict[str, Any] | None, str]:
    text = value.strip()
    if not text.startswith("{"):
        return None, text
    try:
        candidate = json.loads(text)
    except json.JSONDecodeError:
        return None, text
    if not isinstance(candidate, dict) or "request" not in candidate:
        return None, text
    if not isinstance(candidate.get("request"), str) or not candidate["request"].strip():
        raise RequestEnvelopeError("request envelope.request must be a non-empty string")
    if candidate.get("task_type") not in TASK_TYPES or candidate.get("mode") not in MODES:
        raise RequestEnvelopeError("request envelope task_type/mode is invalid")
    if not isinstance(candidate.get("independent_review", False), bool) or not isinstance(candidate.get("sensitive", False), bool):
        raise RequestEnvelopeError("request envelope boolean fields are invalid")
    return candidate, candidate["request"]
