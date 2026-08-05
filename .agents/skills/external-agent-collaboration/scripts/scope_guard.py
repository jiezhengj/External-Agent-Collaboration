"""Normalize and fail-closed validate the Claude tool-scope protocol."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from workspace_context import WorkspaceContextError, link_like


class ScopeGuardError(RuntimeError):
    def __init__(self, message: str, code: str = "scope_guard_protocol_invalid") -> None:
        super().__init__(message)
        self.code = code


READ_TOOLS = {"Read", "Glob", "Grep"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}


def _relative(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ScopeGuardError("candidate path must be project-relative")
    return candidate


def _inside(candidate: Path, allowed: list[Path]) -> bool:
    return any(candidate == item or item in candidate.parents for item in allowed)


def normalize_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScopeGuardError("scope request must be an object")
    required = ("schema_version", "invocation_id", "tool_name", "operation", "parameters", "candidate_paths", "command_argv", "target_project_root", "allowed_paths", "allowed_commands")
    if any(key not in value for key in required):
        raise ScopeGuardError("scope request is missing required fields")
    if value.get("schema_version") != 1:
        raise ScopeGuardError("unsupported scope request schema version")
    if not isinstance(value["invocation_id"], str) or not value["invocation_id"]:
        raise ScopeGuardError("invocation_id must be non-empty")
    if not isinstance(value["tool_name"], str) or not value["tool_name"]:
        raise ScopeGuardError("tool_name must be non-empty")
    if not isinstance(value["operation"], str) or not value["operation"]:
        raise ScopeGuardError("operation must be non-empty")
    if not isinstance(value["parameters"], dict) or not isinstance(value["candidate_paths"], list) or not isinstance(value["command_argv"], list):
        raise ScopeGuardError("scope request fields have invalid types")
    if not isinstance(value["target_project_root"], str) or not Path(value["target_project_root"]).is_absolute():
        raise ScopeGuardError("target_project_root must be absolute")
    if not isinstance(value["allowed_paths"], list) or not all(isinstance(item, str) for item in value["allowed_paths"]):
        raise ScopeGuardError("allowed_paths must be a string array")
    if not isinstance(value["allowed_commands"], list) or not all(isinstance(item, str) and item for item in value["allowed_commands"]):
        raise ScopeGuardError("allowed_commands must be a non-empty string array")
    return value


def check(value: Any) -> dict[str, Any]:
    try:
        request = normalize_request(value)
        root = Path(request["target_project_root"]).resolve()
        allowed = [_relative(root, item) for item in request["allowed_paths"]]
        candidates = [_relative(root, item) for item in request["candidate_paths"]]
        tool = request["tool_name"]
        operation = request["operation"]
        if tool not in READ_TOOLS | WRITE_TOOLS | {"Bash"}:
            raise ScopeGuardError("unknown tool is denied", "scope_guard_denied")
        if not candidates and tool != "Bash":
            raise ScopeGuardError("path-bearing tool supplied no candidate path", "scope_guard_denied")
        if tool in WRITE_TOOLS and operation not in {"write", "delete", "rename"}:
            raise ScopeGuardError("write tool operation is invalid", "scope_guard_denied")
        if tool in READ_TOOLS and operation not in {"read", "list", "search"}:
            raise ScopeGuardError("read tool operation is invalid", "scope_guard_denied")
        if tool == "Bash":
            argv = request["command_argv"]
            if not argv or not all(isinstance(item, str) and item for item in argv):
                raise ScopeGuardError("Bash requires a non-empty argv", "scope_guard_denied")
            command = " ".join(argv)
            if command not in request["allowed_commands"]:
                raise ScopeGuardError("Bash command is not allowlisted", "scope_guard_denied")
        elif not all(_inside(path, allowed) for path in candidates):
            raise ScopeGuardError("candidate path is outside allowed paths", "scope_guard_denied")
        else:
            for relative in candidates:
                current = root / relative
                components = [root / part for part in relative.parents if str(part) != "."] + [current]
                if any(path.exists() and link_like(path) for path in components):
                    raise ScopeGuardError("linked path is not allowed in scope", "linked_path_in_execute_scope")
        return {"schema_version": 1, "decision": "allow", "reason_code": "in_scope", "checked_path_count": len(candidates)}
    except ScopeGuardError as exc:
        return {"schema_version": 1, "decision": "deny", "reason_code": exc.code, "checked_path_count": 0}
    except (OSError, WorkspaceContextError):
        # A link/reparse-point inspection failure is a security failure, not a
        # permissive read failure.  Normalize it so every public check result
        # remains a deny decision and callers never accidentally continue.
        return {"schema_version": 1, "decision": "deny", "reason_code": "scope_guard_unavailable", "checked_path_count": 0}


def execute_hook_available(config_dir: str | Path) -> bool:
    """Detect an explicitly installed native hook; absence is not treated as safe."""
    root = Path(config_dir)
    candidates = (root / "settings.json", root / "hooks.json", root / "hooks" / "scope-guard.json")
    return any(path.is_file() and "scope" in path.read_text(encoding="utf-8", errors="ignore").lower() for path in candidates)


def require_execute_guard(config_dir: str | Path, *, context_only: bool = False, bridge_available: bool = False) -> None:
    if context_only or bridge_available:
        return
    if not execute_hook_available(config_dir):
        raise ScopeGuardError("No verified Claude scope hook is installed; execute is fail-closed.", "scope_guard_unavailable")
