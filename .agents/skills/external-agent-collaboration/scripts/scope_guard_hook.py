"""Claude Code PreToolUse bridge for the Codex-owned ScopeGuard.

Claude invokes this process with the hook event as JSON on stdin.  The bridge
prints only Claude's documented hook decision object; diagnostics never go to
stdout because stdout is part of the protocol.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from scope_guard import ScopeGuardError, check


def _relative(root: Path, value: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ScopeGuardError("hook candidate path is outside target project", "scope_guard_denied") from exc
    if not candidate.parts or ".." in candidate.parts:
        raise ScopeGuardError("hook candidate path is not project-relative", "scope_guard_denied")
    return candidate.as_posix()


def _tool_input(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("tool_input", {})
    return value if isinstance(value, dict) else {}


def _paths(tool: str, value: dict[str, Any], root: Path) -> list[str]:
    raw: list[str] = []
    if tool in {"Read", "Write", "Edit", "NotebookEdit"}:
        for key in ("file_path", "notebook_path", "path"):
            if isinstance(value.get(key), str):
                raw.append(value[key])
    elif tool in {"Glob", "Grep"}:
        for key in ("path", "file_path"):
            if isinstance(value.get(key), str):
                raw.append(value[key])
    return [_relative(root, item) for item in raw]


def _argv(tool: str, value: dict[str, Any]) -> list[str]:
    if tool != "Bash":
        return []
    command = value.get("command")
    if not isinstance(command, str) or not command.strip():
        return []
    try:
        return shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return []


def build_request(event: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ScopeGuardError("Claude hook event must be an object")
    root = Path(str(config["target_project_root"])).resolve()
    tool = event.get("tool_name") or event.get("toolName")
    if not isinstance(tool, str) or not tool:
        raise ScopeGuardError("Claude hook event has no tool_name")
    return {
        "schema_version": 1,
        "invocation_id": str(config.get("invocation_id") or event.get("session_id") or "hook-invocation"),
        "tool_name": tool,
        "operation": "read" if tool in {"Read", "Glob", "Grep"} else "write" if tool in {"Edit", "Write", "NotebookEdit"} else "execute",
        "parameters": _tool_input(event),
        "candidate_paths": _paths(tool, _tool_input(event), root),
        "command_argv": _argv(tool, _tool_input(event)),
        "target_project_root": str(root),
        "allowed_paths": [str(item) for item in config.get("allowed_paths", [])],
        "allowed_commands": [str(item) for item in config.get("allowed_commands", [])],
    }


def decision(result: dict[str, Any]) -> dict[str, Any]:
    allowed = result.get("decision") == "allow"
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if allowed else "deny",
            "permissionDecisionReason": str(result.get("reason_code", "scope_guard_denied")),
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        event = json.load(sys.stdin)
        result = check(build_request(event, config))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ScopeGuardError) as exc:
        result = {"schema_version": 1, "decision": "deny", "reason_code": "scope_guard_protocol_invalid"}
        print(f"scope hook denied: {type(exc).__name__}", file=sys.stderr)
    sys.stdout.write(json.dumps(decision(result), ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
