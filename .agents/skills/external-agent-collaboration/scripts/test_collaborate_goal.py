#!/usr/bin/env python3
"""Integration regression for --goal-contract without a provider call."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("collaborate.py")
SPEC = importlib.util.spec_from_file_location("collaborate", SCRIPT)
assert SPEC and SPEC.loader
collaborate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collaborate)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="collaborate-goal-test-") as directory:
        root = Path(directory)
        control = root / ".ai-collaboration"
        handoff = root / "handoff.md"
        contract = root / "goal.json"
        config = root / "config"
        config.mkdir(parents=True)
        handoff.write_text("Review this bounded local topic.", encoding="utf-8")
        contract.write_text(json.dumps({
            "schema_version": 1,
            "goal_id": "integration-goal",
            "success_criteria": [{"id": "acceptance", "required": True, "verification": "user_acceptance"}],
            "completion_policy": {"require_all": True, "review": "none", "user_acceptance": "required", "platforms": []},
            "stop_policy": {"max_attempts": 2, "on_blocked": "pause"},
        }), encoding="utf-8")

        original = {
            "PROJECT_ROOT": collaborate.PROJECT_ROOT,
            "CONTROL_ROOT": collaborate.CONTROL_ROOT,
            "TRUST_FILE": collaborate.TRUST_FILE,
            "SESSIONS_FILE": collaborate.SESSIONS_FILE,
            "METRICS_FILE": collaborate.METRICS_FILE,
            "HEALTH_FILE": collaborate.HEALTH_FILE,
            "TOPICS_FILE": collaborate.TOPICS_FILE,
            "GOALS_DIR": collaborate.GOALS_DIR,
        }
        collaborate.PROJECT_ROOT = root
        collaborate.CONTROL_ROOT = control
        collaborate.TRUST_FILE = control / "trusted-providers.local.json"
        collaborate.SESSIONS_FILE = control / "sessions.json"
        collaborate.METRICS_FILE = control / "provider-metrics.json"
        collaborate.HEALTH_FILE = control / "provider-health.json"
        collaborate.TOPICS_FILE = control / "topics.json"
        collaborate.GOALS_DIR = control / "goals"
        response = {"summary": "ok", "changed_files": [], "commands_run": [], "validation_results": [], "risks": [], "uncertainty": ""}
        fake_result = {"result": json.dumps(response), "session_id": "session-1"}
        argv = [
            "collaborate.py", "--action", "consult", "--provider", "provider_a", "--topic", "integration", "--handoff", str(handoff),
            "--working-directory", str(root), "--goal-contract", "goal.json", "--topic-goal", "Integration Goal", "--stop-rule", "Wait for explicit acceptance",
        ]
        old_argv = sys.argv
        try:
            sys.argv = argv
            with patch.object(collaborate, "profiles", return_value={"provider_a": {"config_dir": str(config), "launcher": "claude"}}), \
                patch.object(collaborate, "trust_registry", return_value={"providers": {}}), \
                patch.object(collaborate, "trusted_profiles", side_effect=lambda configured, _trust: configured), \
                patch.object(collaborate, "profile_problem", return_value=None), \
                patch.object(collaborate, "invoke", return_value=(0, "", "")), \
                patch.object(collaborate, "parse_result", return_value=fake_result):
                assert collaborate.main() == 0
        finally:
            sys.argv = old_argv
            for name, value in original.items():
                setattr(collaborate, name, value)

        state_path = control / "goals" / "integration-goal.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "active" and state["attempts"] == 1
        output_files = list((control / "outputs").glob("*.json"))
        assert output_files
        result = json.loads(output_files[0].read_text(encoding="utf-8"))
        assert result["goal"]["goal_id"] == "integration-goal"
        assert "Goal state:" in next(path for path in (control / "topics").glob("*.md")).read_text(encoding="utf-8")
    print("collaborate-goal tests passed")


if __name__ == "__main__":
    main()
