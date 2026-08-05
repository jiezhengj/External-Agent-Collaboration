#!/usr/bin/env python3
"""Sibling-repository target context and router cwd regression."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import collaborate
import route_harness


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cross-project-") as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        workdir = root / "src"; workdir.mkdir()
        context = collaborate.resolve_context(str(workdir))
        assert context.cross_project is True
        assert context.target_project_root == root.resolve()
        collaborate.configure_context(context)
        values = {"action": "consult", "provider": "deepseek", "topic": "cross", "handoff": "handoff.md", "working_directory": str(workdir), "return_mode": "compact", "response_contract": "standard", "timeout": 120, "session_key": None, "expected_response": None, "task_type": "code", "mode": "analyze", "expected_outcomes": None, "topic_goal": None, "stop_rule": None, "goal_contract": None, "goal_state": None, "allow_path": [], "allow_delete": [], "allow_binary_path": [], "allow_command": [], "validation_command": [], "validation_argv": [], "fork_session": False, "ephemeral": True, "stream_diagnostics": False, "max_cost_usd": None, "max_duration_seconds": None, "max_provider_attempts": 2, "project_root": str(root), "invocation_id": "inv-cross"}
        command = route_harness.claude_command(argparse.Namespace(**values), "default_project_collaborator")
        assert "--project-root" in command and str(root) in command and route_harness.collaborate.CONTEXT.target_workdir == workdir.resolve()
    print("cross-project invocation tests passed")


if __name__ == "__main__":
    main()
