#!/usr/bin/env python3
"""Local, content-free provider availability state for the collaboration runner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from harness_state import state_identity
from platform_support import host_platform


LONG_COOLDOWN_KINDS = {"billing", "authentication", "endpoint", "configuration"}
TRANSIENT_COOLDOWNS = (5, 15, 60, 360)  # minutes, capped at six hours


def default_health() -> dict[str, Any]:
    return {"schema_version": 1, "providers": {}}


def valid_health(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("providers"), dict):
        return default_health()
    data.setdefault("schema_version", 1)
    return data


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def timestamp(value: datetime | None = None) -> datetime:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc)


def is_available(data: dict[str, Any], provider: str, at: datetime | None = None) -> bool:
    record = data.get("providers", {}).get(provider)
    if not isinstance(record, dict) or record.get("state") != "open":
        return True
    retry_after = parse_time(record.get("retry_after"))
    return retry_after is None or timestamp(at) >= retry_after


def status(data: dict[str, Any], provider: str, at: datetime | None = None) -> dict[str, Any]:
    record = data.get("providers", {}).get(provider)
    if not isinstance(record, dict) or is_available(data, provider, at):
        return {"state": "healthy"}
    return {
        "state": "open",
        "failure_kind": record.get("failure_kind"),
        "retry_after": record.get("retry_after"),
    }


def record_failure(data: dict[str, Any], provider: str, kind: str, at: datetime | None = None, harness: str = "claude_code", harness_profile: str | None = None) -> dict[str, Any]:
    current = data.setdefault("providers", {}).get(provider)
    prior_count = int(current.get("failure_count", 0)) if isinstance(current, dict) else 0
    when = timestamp(at)
    if isinstance(current, dict):
        retry_after = parse_time(current.get("retry_after"))
        if retry_after is not None and when >= retry_after:
            prior_count = 0
    count = prior_count + 1
    if kind in LONG_COOLDOWN_KINDS:
        minutes = 24 * 60
    else:
        minutes = TRANSIENT_COOLDOWNS[min(count - 1, len(TRANSIENT_COOLDOWNS) - 1)]
    record = {
        "state": "open",
        "failure_kind": kind,
        "failure_count": count,
        "opened_at": when.isoformat(),
        "retry_after": (when + timedelta(minutes=minutes)).isoformat(),
        "harness": harness,
        "harness_profile": harness_profile or provider,
        "state_identity": state_identity(harness, harness_profile or provider, host_platform()),
    }
    data["providers"][provider] = record
    return record


def record_success(data: dict[str, Any], provider: str, at: datetime | None = None, harness: str = "claude_code", harness_profile: str | None = None) -> None:
    data.setdefault("providers", {})[provider] = {
        "state": "healthy", "last_success_at": timestamp(at).isoformat(),
        "harness": harness, "harness_profile": harness_profile or provider,
        "state_identity": state_identity(harness, harness_profile or provider, host_platform()),
    }


def classify_failure(exit_code: int, stderr: str) -> str | None:
    """Classify only high-confidence availability failures; never persist source text."""
    text = stderr.lower()
    if any(value in text for value in ("insufficient balance", "insufficient account balance", "insufficient quota", "payment required", "billing", "http 402")):
        return "billing"
    if any(value in text for value in ("invalid api key", "authentication", "unauthorized", "http 401", "http 403")):
        return "authentication"
    if any(value in text for value in ("base url", "endpoint", "certificate verify", "ssl", "dns", "name or service not known")):
        return "endpoint"
    if any(value in text for value in ("rate limit", "too many requests", "http 429")):
        return "rate_limit"
    if exit_code == 124 or any(value in text for value in ("timed out", "timeout", "connection reset", "connection refused", "network is unreachable")):
        return "transport"
    if any(value in text for value in ("http 500", "http 502", "http 503", "http 504", "internal server error", "service unavailable")):
        return "server"
    return None
