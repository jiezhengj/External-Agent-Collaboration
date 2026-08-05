#!/usr/bin/env python3
"""Scope protocol fail-closed tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from scope_guard import check, require_execute_guard, ScopeGuardError


def request(**changes: object) -> dict:
    value = {"schema_version": 1, "invocation_id": "inv-1", "tool_name": "Read", "operation": "read", "parameters": {}, "candidate_paths": ["docs/a.md"], "command_argv": [], "target_project_root": str(Path.cwd()), "allowed_paths": ["docs"], "allowed_commands": ["python -m pytest"]}
    value.update(changes)
    return value


def main() -> None:
    assert check(request())["decision"] == "allow"
    assert check(request(candidate_paths=["../secret"]))["decision"] == "deny"
    assert check(request(tool_name="Unknown"))["reason_code"] == "scope_guard_denied"
    bash = request(tool_name="Bash", operation="execute", candidate_paths=[], command_argv=["python -m pytest"])
    assert check(bash)["decision"] == "allow"
    bash["command_argv"] = ["rm", "-rf", "."]
    assert check(bash)["decision"] == "deny"
    with tempfile.TemporaryDirectory(prefix="scope-guard-") as directory:
        project = Path(directory)
        (project / "docs").mkdir()
        (project / "outside").mkdir()
        try:
            (project / "docs" / "link").symlink_to(project / "outside", target_is_directory=True)
            linked = request(target_project_root=str(project), candidate_paths=["docs/link/file.txt"])
            assert check(linked)["reason_code"] == "linked_path_in_execute_scope"
        except (OSError, NotImplementedError):
            pass
        try:
            require_execute_guard(directory)
        except ScopeGuardError as exc:
            assert exc.code == "scope_guard_unavailable"
        else:
            raise AssertionError("execute must fail closed without a verified hook")
    print("scope-guard tests passed")


if __name__ == "__main__":
    main()
