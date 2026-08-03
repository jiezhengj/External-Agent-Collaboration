#!/usr/bin/env python3
"""Regression tests for routing policy precedence in the Claude runner."""

from __future__ import annotations

import tempfile
from pathlib import Path

import collaborate
import provider_health


def profiles(root: Path) -> dict[str, dict[str, str]]:
    return {"deepseek": {"config_dir": str(root)}, "mimo": {"config_dir": str(root)}}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="collaborate-routing-test-") as directory:
        root = Path(directory)
        available = profiles(root)
        metrics = {"schema_version": 2, "round_robin_cursor": {}, "routing_state": {}, "events": []}
        health = provider_health.default_health()
        fixed = {"schema_version": 1, "default": {"strategy": "fixed", "provider": "deepseek"}, "task_overrides": {}}

        selected, session, auto, route = collaborate.select_provider("auto", "fresh", root, [], available, metrics, health, "research", "analyze", fixed)
        assert selected == "deepseek" and session is None and auto and route["basis"] == "configured_fixed"

        selected, session, auto, route = collaborate.select_provider("mimo", "fresh", root, [], available, metrics, health, "research", "analyze", fixed)
        assert selected == "mimo" and session is None and not auto and route["basis"] == "user_specified"

        active_session = {
            "status": "active", "topic": "continued", "working_directory": str(root),
            "workspace_identity": collaborate.workspace_identity(root), "host_platform": collaborate.host_platform(),
            "provider": "mimo", "key": "mimo-session", "harness": collaborate.CLAUDE_CODE,
        }
        selected, session, auto, route = collaborate.select_provider("auto", "continued", root, [active_session], available, metrics, health, "research", "analyze", fixed)
        assert selected == "mimo" and session is active_session and not auto and route["basis"] == "exact_active_session"

        provider_health.record_failure(health, "deepseek", "billing")
        fallback = collaborate.alternate_provider("deepseek", available, metrics, health, "research", "analyze")
        assert fallback is not None
        fallback_provider, _fallback_profile, fallback_route = fallback
        assert fallback_provider == "mimo" and fallback_route["basis"] == "availability_failover"
        try:
            collaborate.select_provider("auto", "blocked", root, [], available, metrics, health, "research", "analyze", fixed)
        except collaborate.CollaborationError as exc:
            assert "fixed_provider_unavailable" in str(exc)
        else:
            raise AssertionError("fixed pre-call cooldown must fail closed")
    print("collaborate-routing tests passed")


if __name__ == "__main__":
    main()
