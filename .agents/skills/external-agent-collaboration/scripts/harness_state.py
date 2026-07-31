"""Claude-first helpers for harness-scoped runtime records and safe migration."""

from __future__ import annotations

import os
from typing import Any


CLAUDE_CODE = "claude_code"
CLAUDE_SESSION_KIND = "claude_session"
RUNTIME_SCHEMA_VERSION = 3


def state_feature_enabled() -> bool:
    """Future harness routing is opt-in; the current Claude route stays default."""
    return os.environ.get("EXTERNAL_AGENT_HARNESS_STATE") == "1"


def state_identity(harness: str, harness_profile: str, host_platform: str | None = None) -> str:
    platform = host_platform or "unknown"
    return f"{harness}:{harness_profile}:{platform}"


def session_harness(session: dict[str, Any]) -> str:
    value = session.get("harness", CLAUDE_CODE)
    return value if isinstance(value, str) and value else CLAUDE_CODE


def session_profile(session: dict[str, Any]) -> str:
    value = session.get("harness_profile") or session.get("model_profile") or session.get("provider")
    return str(value) if value is not None else "unknown"


def external_session_id(session: dict[str, Any]) -> str | None:
    value = session.get("external_session_id") or session.get("session_id")
    return value if isinstance(value, str) and value else None


def claude_session_record(provider: str, host_platform: str, external_id: str) -> dict[str, str]:
    return {
        "harness": CLAUDE_CODE,
        "harness_profile": provider,
        "external_session_id": external_id,
        "session_kind": CLAUDE_SESSION_KIND,
        "state_identity": state_identity(CLAUDE_CODE, provider, host_platform),
    }


def decorate_legacy_record(record: dict[str, Any], provider: str | None = None, host_platform: str | None = None) -> bool:
    """Annotate legacy Claude records without dropping legacy compatibility fields."""
    if record.get("harness") not in {None, CLAUDE_CODE}:
        return False
    changed = False
    resolved_profile = str(record.get("harness_profile") or provider or record.get("model_profile") or record.get("provider") or "unknown")
    resolved_platform = str(record.get("host_platform") or host_platform or "unknown")
    defaults = {
        "harness": CLAUDE_CODE,
        "harness_profile": resolved_profile,
        "state_identity": state_identity(CLAUDE_CODE, resolved_profile, resolved_platform),
    }
    if isinstance(record.get("session_id"), str) and "external_session_id" not in record:
        defaults["external_session_id"] = record["session_id"]
        defaults["session_kind"] = CLAUDE_SESSION_KIND
    for key, value in defaults.items():
        if key not in record:
            record[key] = value
            changed = True
    return changed
