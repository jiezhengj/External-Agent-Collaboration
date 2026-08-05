#!/usr/bin/env python3
"""Tests for the actual Claude PreToolUse JSON bridge."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scope_guard_hook import build_request, decision
from scope_guard import check


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scope-hook-") as directory:
        root = Path(directory)
        config = {"schema_version": 1, "invocation_id": "hook-1", "target_project_root": str(root), "allowed_paths": ["docs"], "allowed_commands": ["python -m pytest"]}
        (root / "docs").mkdir()
        allowed = build_request({"tool_name": "Write", "tool_input": {"file_path": str(root / "docs" / "a.md")}}, config)
        assert decision({"decision": "allow", "reason_code": "in_scope"})["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert allowed["candidate_paths"] == ["docs/a.md"]
        (root / "docs" / "inside").mkdir()
        try:
            (root / "docs" / "alias").symlink_to(root / "docs" / "inside", target_is_directory=True)
            linked = build_request({"tool_name": "Write", "tool_input": {"file_path": str(root / "docs" / "alias" / "file.md")}}, config)
            assert decision(check(linked))["hookSpecificOutput"]["permissionDecision"] == "deny"
        except (OSError, NotImplementedError):
            pass
        denied = build_request({"tool_name": "Bash", "tool_input": {"command": "rm -rf ."}}, config)
        assert decision({"decision": "deny", "reason_code": "scope_guard_denied"})["hookSpecificOutput"]["permissionDecision"] == "deny"
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("scope_guard_hook.py")), "--config", str(config_path)],
            input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(root / "outside.md")}}) + "\n",
            text=True, capture_output=True, check=False,
        )
        payload = json.loads(completed.stdout)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert completed.returncode == 0
    print("scope-guard-hook tests passed")


if __name__ == "__main__":
    main()
