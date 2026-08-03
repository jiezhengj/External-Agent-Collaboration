#!/usr/bin/env python3
"""Regression tests for multi-run Goal validation, aggregation and terminal states."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("goal_lifecycle.py")
SPEC = importlib.util.spec_from_file_location("goal_lifecycle", SCRIPT)
assert SPEC and SPEC.loader
goal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(goal)


def run(run_id: str, status: str, platform: str, outcomes: list[dict]) -> dict:
    return {
        "run_id": run_id,
        "status": status,
        "action": "execute",
        "host_platform": platform,
        "output_path": f".ai-collaboration/outputs/{run_id}.json",
        "outcome_results": outcomes,
    }


def outcome(kind: str, passed: bool, **expected: object) -> dict:
    return {"type": kind, "passed": passed, "expected": {"type": kind, **expected}, **{key: value for key, value in expected.items() if key in {"path", "command", "argv"}}}


def contract(max_attempts: int = 5) -> dict:
    return {
        "schema_version": 1,
        "goal_id": "goal-lifecycle-test",
        "success_criteria": [
            {"id": "artifact", "required": True, "verification": "file_exists", "path": "docs/result.md"},
            {"id": "macos", "required": True, "verification": "file_contains", "path": "docs/result.md", "text": "done", "platform": "macos"},
            {"id": "windows", "required": True, "verification": "file_exists", "path": "docs/result.md", "platform": "windows"},
            {"id": "review", "required": True, "verification": "review", "platform": "macos"},
            {"id": "acceptance", "required": True, "verification": "user_acceptance"},
        ],
        "completion_policy": {"require_all": True, "review": "independent", "user_acceptance": "required", "platforms": ["macos", "windows"]},
        "stop_policy": {"max_attempts": max_attempts, "on_blocked": "pause"},
    }


def main() -> None:
    current = goal.validate_contract(contract())
    state = goal.new_state(current)
    state = goal.record_run(state, current, run("run-artifact", "completed", "macos", [outcome("file_exists", True, path="docs/result.md")]))
    assert state["status"] == "active"
    assert state["criteria"]["artifact"]["status"] == "passed"

    state = goal.record_run(state, current, run("run-macos", "completed", "macos", [outcome("file_contains", True, path="docs/result.md", text="done")]))
    assert state["criteria"]["macos"]["status"] == "passed"
    assert state["status"] == "active", "A completed Run must not imply Goal achievement."

    state = goal.record_run(state, current, run("run-windows", "completed", "windows", [outcome("file_exists", True, path="docs/result.md")]))
    assert state["criteria"]["windows"]["status"] == "passed"
    state = goal.apply_decision(state, current, "review", "passed", [".ai-collaboration/reviews/review.json"], "reviewer", "Independent review passed.")
    assert state["status"] == "active"
    state = goal.apply_decision(state, current, "acceptance", "passed", ["user:accepted"], "user", "User accepted the result.")
    assert state["status"] == "achieved"
    assert state["close"]["status"] == "achieved"

    rerun = goal.new_state(current)
    rerun = goal.record_run(rerun, current, run("run-failed", "failed", "macos", [outcome("file_exists", False, path="docs/result.md")]))
    rerun = goal.record_run(rerun, current, run("run-recovered", "completed", "macos", [outcome("file_exists", True, path="docs/result.md")]))
    assert rerun["criteria"]["artifact"]["status"] == "passed"
    assert rerun["status"] == "active", "A later completed Run must not erase other pending Goal criteria."

    na_contract = goal.validate_contract({
        "schema_version": 1,
        "goal_id": "not-applicable-goal",
        "success_criteria": [{"id": "windows-only", "required": True, "verification": "file_exists", "path": "docs/result.md"}],
        "completion_policy": {"require_all": True, "platforms": []},
        "stop_policy": {"max_attempts": 2, "on_blocked": "pause"},
    })
    na_state = goal.new_state(na_contract)
    try:
        goal.apply_decision(na_state, na_contract, "windows-only", "not_applicable", [], "codex", "")
    except goal.GoalError:
        pass
    else:
        raise AssertionError("not_applicable without reason/evidence must fail closed.")
    na_state = goal.apply_decision(na_state, na_contract, "windows-only", "not_applicable", ["platform-policy.md"], "codex", "Windows is not in this Goal scope.")
    assert na_state["status"] == "achieved"

    blocked_contract = goal.validate_contract({**contract(), "goal_id": "blocked-goal"})
    blocked = goal.new_state(blocked_contract)
    blocked = goal.block_goal(blocked, blocked_contract, "Needs external approval", "maintainer", "Approval record exists", ["ticket:123"])
    assert blocked["status"] == "blocked" and blocked["close"]["status"] == "blocked"
    blocked = goal.unblock_goal(blocked, blocked_contract, ["ticket:123:approved"])
    assert blocked["status"] == "active" and blocked["close"] is None
    blocked = goal.cancel_goal(blocked, blocked_contract, "user", "No longer needed")
    assert blocked["status"] == "cancelled"

    retry_contract = goal.validate_contract({**contract(), "goal_id": "retry-goal", "stop_policy": {"max_attempts": 2, "on_blocked": "pause"}})
    retry = goal.new_state(retry_contract)
    retry = goal.record_run(retry, retry_contract, run("retry-1", "failed", "macos", [outcome("file_exists", False, path="docs/result.md")]))
    assert retry["status"] == "active"
    retry = goal.record_run(retry, retry_contract, run("retry-2", "completed", "macos", [outcome("file_exists", True, path="docs/result.md")]))
    assert retry["status"] == "failed", "Unmet required criteria at max_attempts must fail the Goal."

    invalid = {**contract(), "goal_id": "invalid-goal", "success_criteria": [{"id": "bad", "required": True, "verification": "test"}]}
    try:
        goal.validate_contract(invalid)
    except goal.GoalError:
        pass
    else:
        raise AssertionError("Unsupported verification must fail closed.")

    with tempfile.TemporaryDirectory(prefix="goal-lifecycle-test-") as directory:
        root = Path(directory)
        contract_path = root / "goal.json"
        state_path = root / ".ai-collaboration" / "goals" / "goal-lifecycle-test.json"
        contract_path.write_text(json.dumps(current), encoding="utf-8")
        loaded = goal.load_contract(contract_path)
        fresh = goal.load_state(state_path, loaded, "goal.json")
        goal.save_state(state_path, fresh)
        assert state_path.is_file()
        assert goal.cli(["--project-root", str(root), "validate", "--contract", "goal.json"]) == 0
        assert goal.cli(["--project-root", str(root), "show", "--contract", "goal.json"]) == 0
        run_path = root / "run.json"
        run_path.write_text(json.dumps(run("cli-run", "completed", "macos", [])), encoding="utf-8")
        assert goal.cli(["--project-root", str(root), "record-run", "--contract", "goal.json", "--run-record", "run.json"]) == 0
        assert json.loads(state_path.read_text(encoding="utf-8"))["attempts"] == 1

    print("goal-lifecycle tests passed")


if __name__ == "__main__":
    main()
