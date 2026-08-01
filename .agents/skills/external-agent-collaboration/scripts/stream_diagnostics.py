"""Parse headless NDJSON without retaining model text, prompts, or raw events."""

from __future__ import annotations

import json
from typing import Any


class StreamDiagnosticsError(RuntimeError):
    pass


def _contains(value: Any, markers: tuple[str, ...]) -> bool:
    """Inspect an event transiently; callers persist only the resulting boolean."""
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":")).lower()
    except (TypeError, ValueError):
        return False
    return any(marker in text for marker in markers)


def parse_ndjson(stdout: str, *, stream_kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return one terminal envelope and a compact, content-free diagnostic summary.

    ``stream_kind`` is ``claude`` (terminal record is the event itself) or
    ``antigravity`` (terminal record is under ``result``).  Unknown event
    payloads are deliberately reduced to counters and booleans.
    """
    if stream_kind not in {"claude", "antigravity"}:
        raise StreamDiagnosticsError("Unknown stream diagnostics kind.")
    diagnostics: dict[str, Any] = {
        "format": "stream-json",
        "event_count": 0,
        "invalid_line_count": 0,
        "event_types": {},
        "startup_observed": False,
        "api_retry_count": 0,
        "permission_signal_count": 0,
        "plugin_or_mcp_failure": False,
        "terminal_observed": False,
        "write_tool_available": False,
        "permission_mode": None,
        "step_types": {},
        "write_tool_step_count": 0,
    }
    terminal: dict[str, Any] | None = None
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            diagnostics["invalid_line_count"] += 1
            continue
        if not isinstance(event, dict):
            diagnostics["invalid_line_count"] += 1
            continue
        event_type = str(event.get("type") or event.get("event") or "unknown")[:80]
        counts = diagnostics["event_types"]
        counts[event_type] = min(int(counts.get(event_type, 0)) + 1, 10_000)
        diagnostics["event_count"] += 1
        is_startup = (
            (stream_kind == "claude" and event_type == "system" and str(event.get("subtype", "")) == "init")
            or (stream_kind == "antigravity" and event_type == "init")
        )
        diagnostics["startup_observed"] = diagnostics["startup_observed"] or is_startup
        if stream_kind == "antigravity" and event_type == "init" and isinstance(event.get("init"), dict):
            init = event["init"]
            tools = init.get("tools")
            diagnostics["write_tool_available"] = isinstance(tools, list) and "write_to_file" in tools
            mode = init.get("permission_mode")
            diagnostics["permission_mode"] = str(mode)[:80] if isinstance(mode, str) else None
        if stream_kind == "antigravity" and event_type == "step_update" and isinstance(event.get("step_update"), dict):
            step_type = str(event["step_update"].get("step_type", "unknown"))[:80]
            diagnostics["step_types"][step_type] = min(int(diagnostics["step_types"].get(step_type, 0)) + 1, 10_000)
            if "write" in step_type.lower():
                diagnostics["write_tool_step_count"] += 1
        if _contains(event, ("retry", "rate_limit", "rate limit")):
            diagnostics["api_retry_count"] = min(int(diagnostics["api_retry_count"]) + 1, 10_000)
        if _contains(event, ("permission", "approval", "soft-denied", "soft denied")):
            diagnostics["permission_signal_count"] = min(int(diagnostics["permission_signal_count"]) + 1, 10_000)
        if _contains(event, ("plugin", "mcp")) and _contains(event, ("error", "failed", "failure", "unavailable", "denied")):
            diagnostics["plugin_or_mcp_failure"] = True
        is_terminal = event_type == "result"
        if is_terminal:
            candidate = event.get("result") if stream_kind == "antigravity" else event
            if isinstance(candidate, dict):
                terminal = candidate
                diagnostics["terminal_observed"] = True
                status = candidate.get("status")
                if isinstance(status, str):
                    diagnostics["terminal_status"] = status[:80]
    if terminal is None:
        raise StreamDiagnosticsError("stream-json output has no terminal result event.")
    return terminal, diagnostics
