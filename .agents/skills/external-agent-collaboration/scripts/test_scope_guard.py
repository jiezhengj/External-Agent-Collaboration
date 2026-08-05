#!/usr/bin/env python3
"""Scope protocol fail-closed tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from scope_guard import check, execute_hook_available, normalize_request, require_execute_guard, ScopeGuardError


def request(**changes: object) -> dict:
    value = {"schema_version": 1, "invocation_id": "inv-1", "tool_name": "Read", "operation": "read", "parameters": {}, "candidate_paths": ["docs/a.md"], "command_argv": [], "target_project_root": str(Path.cwd()), "allowed_paths": ["docs"], "allowed_commands": ["python -m pytest"]}
    value.update(changes)
    return value


def main() -> None:
    for invalid in (None, {}, {"schema_version": 2}):
        try:
            normalize_request(invalid)
        except ScopeGuardError:
            pass
        else:
            raise AssertionError("invalid scope request must be rejected")
    assert check(request())["decision"] == "allow"
    assert check(request(candidate_paths=["../secret"]))["decision"] == "deny"
    assert check(request(tool_name="Unknown"))["reason_code"] == "scope_guard_denied"
    bash = request(tool_name="Bash", operation="execute", candidate_paths=[], command_argv=["python -m pytest"])
    assert check(bash)["decision"] == "allow"
    bash["command_argv"] = ["rm", "-rf", "."]
    assert check(bash)["decision"] == "deny"
    assert check(request(tool_name="Write", operation="read"))["decision"] == "deny"
    assert check(request(tool_name="Read", operation="write"))["decision"] == "deny"
    assert check(request(tool_name="Bash", operation="execute", candidate_paths=[], command_argv=[]))["decision"] == "deny"
    assert check(request(tool_name="Read", candidate_paths=[]))["decision"] == "deny"
    assert check(request(allowed_commands=[""]))["decision"] == "deny"
    malformed = request()
    malformed["target_project_root"] = "relative"
    assert check(malformed)["decision"] == "deny"
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
        settings = project / "settings.json"
        settings.write_text('{"scope": "verified"}', encoding="utf-8")
        assert execute_hook_available(project) is True
        with patch("scope_guard.link_like", side_effect=OSError):
            assert check(linked)["decision"] == "deny"
    print("scope-guard tests passed")


if __name__ == "__main__":
    main()
