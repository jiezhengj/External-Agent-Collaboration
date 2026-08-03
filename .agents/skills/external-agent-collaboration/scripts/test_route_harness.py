#!/usr/bin/env python3
"""Regression checks for the public P4 harness-role router."""

from __future__ import annotations

import argparse
from pathlib import Path

import route_harness


def args(**changes: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "action": "consult", "harness": "auto", "antigravity_profile": "antigravity_readonly", "request": "请给我第二方案", "provider": "auto", "topic": "review", "handoff": "docs/handoff.md", "working_directory": ".", "session_key": None, "fork_session": False, "allow_path": [], "allow_delete": [], "allow_binary_path": [], "allow_command": [], "expected_outcomes": None, "validation_command": [], "validation_argv": [], "task_type": "planning", "mode": "critique", "timeout": 120, "ephemeral": False, "return_mode": "compact", "response_contract": "standard", "expected_response": None, "stream_diagnostics": False, "topic_goal": None, "stop_rule": None, "goal_contract": None, "goal_state": None,
    }
    values.update(changes)
    return argparse.Namespace(**values)


def main() -> None:
    original_ready = route_harness.antigravity_readiness
    route_harness.antigravity_readiness = lambda _profile: (True, "ready")
    try:
        workdir = Path.cwd()
        selected, detail = route_harness.choose_route(args(), "Request a second opinion.", workdir, [])
        assert selected == route_harness.ANTIGRAVITY and detail["basis"] == "explicit_independent_review"
        command = route_harness.antigravity_command(args(), detail["basis"])
        assert Path(command[1]).name == "consult_antigravity.py" and "--routing-basis" in command
        selected, detail = route_harness.choose_route(args(request="implement this change", action="execute", mode="execute"), "implement this change", workdir, [])
        assert selected == route_harness.CLAUDE_CODE and detail["basis"] == "default_project_collaborator"
        command = route_harness.claude_command(args(action="execute", request="implement this change", mode="execute"), detail["basis"])
        assert Path(command[1]).name == "collaborate.py" and "--harness-routing-basis" in command
        goal_command = route_harness.claude_command(args(goal_contract="docs/goal.json", goal_state=".ai-collaboration/goals/goal.json"), detail["basis"])
        assert "--goal-contract" in goal_command and "--goal-state" in goal_command
        try:
            route_harness.antigravity_command(args(goal_contract="docs/goal.json"), "explicit_independent_review")
        except route_harness.collaborate.CollaborationError:
            pass
        else:
            raise AssertionError("Antigravity must not silently drop Goal aggregation.")
        selected, detail = route_harness.choose_route(args(request="ordinary consultation"), "ordinary consultation", workdir, [])
        assert selected == route_harness.CLAUDE_CODE and detail["basis"] == "default_project_collaborator"
        session = {"key": "agy-session", "status": "active", "topic": "review", "harness": "antigravity", "working_directory": str(workdir), "workspace_identity": route_harness.collaborate.workspace_identity(workdir), "host_platform": route_harness.collaborate.host_platform()}
        selected, detail = route_harness.choose_route(args(session_key="agy-session", action="continue", request="continue"), "continue", workdir, [session])
        assert selected == route_harness.ANTIGRAVITY and detail["basis"] == "explicit_session_key"
        try:
            route_harness.choose_route(args(session_key="agy-session", action="execute", request="execute"), "execute", workdir, [session])
        except route_harness.collaborate.CollaborationError:
            pass
        else:
            raise AssertionError("Antigravity session must remain read-only.")
        route_harness.antigravity_readiness = lambda _profile: (False, "profile_or_trust_not_ready")
        try:
            route_harness.choose_route(args(), "Request a second opinion.", workdir, [])
        except route_harness.collaborate.CollaborationError:
            pass
        else:
            raise AssertionError("An unavailable independent-review role must not silently route to Claude Code.")
        try:
            route_harness.antigravity_command(args(response_contract="none"), "explicit_independent_review")
        except route_harness.collaborate.CollaborationError:
            pass
        else:
            raise AssertionError("Antigravity role routing must preserve the standard structured contract.")
    finally:
        route_harness.antigravity_readiness = original_ready
    print("route-harness tests passed")


if __name__ == "__main__":
    main()
