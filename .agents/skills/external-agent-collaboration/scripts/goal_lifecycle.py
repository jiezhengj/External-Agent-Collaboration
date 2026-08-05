#!/usr/bin/env python3
"""Validate and aggregate persistent multi-run Goal state."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from state_store import locked
from workspace_context import skill_project_root


SCHEMA_VERSION = 1
GOAL_STATUSES = ("active", "achieved", "blocked", "failed", "cancelled")
CRITERION_STATUSES = ("pending", "passed", "failed", "not_applicable")
RUN_STATUSES = ("completed", "failed", "needs_review", "blocked_by_permission")
MACHINE_VERIFICATIONS = {
    "file_exists",
    "file_contains",
    "file_equals",
    "changed_paths",
    "command_succeeds",
    "json_schema",
}
MANUAL_VERIFICATIONS = {"user_acceptance", "review"}
VERIFICATIONS = MACHINE_VERIFICATIONS | MANUAL_VERIFICATIONS
GOAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,80}$")
SAFE_SELECTOR_KEYS = ("type", "path", "text", "command", "argv", "min", "max", "schema")


class GoalError(ValueError):
    """Raised when a Goal contract or state violates the documented protocol."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GoalError(f"Goal file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GoalError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GoalError(message)


def _relative_path(value: Any, field: str) -> None:
    _require(isinstance(value, str) and value.strip(), f"{field} must be a non-empty project-relative path.")
    path = Path(value)
    _require(not path.is_absolute() and ".." not in path.parts, f"{field} must be project-relative and contain no '..'.")
    _require(not any(part in {".env", "secrets", "credentials", "private"} or part.startswith(".env") for part in path.parts), f"{field} may not target sensitive paths.")


def _validate_criterion(criterion: Any, index: int, platforms: list[str]) -> str:
    _require(isinstance(criterion, dict), f"success_criteria[{index}] must be an object.")
    criterion_id = criterion.get("id")
    _require(isinstance(criterion_id, str) and GOAL_ID_PATTERN.fullmatch(criterion_id) is not None, f"success_criteria[{index}].id is invalid.")
    _require(isinstance(criterion.get("required"), bool), f"criterion {criterion_id}.required must be boolean.")
    verification = criterion.get("verification")
    _require(verification in VERIFICATIONS, f"criterion {criterion_id} uses unsupported verification '{verification}'.")
    platform = criterion.get("platform")
    if platform is not None:
        _require(platform in {"macos", "windows"}, f"criterion {criterion_id}.platform must be macos or windows.")
        _require(not platforms or platform in platforms, f"criterion {criterion_id}.platform is not listed in completion_policy.platforms.")

    selector = criterion.get("outcome")
    if selector is not None:
        _require(isinstance(selector, dict), f"criterion {criterion_id}.outcome must be an object.")
        _require(selector.get("type", verification) == verification, f"criterion {criterion_id}.outcome.type must match verification.")
        for key in selector:
            _require(key in SAFE_SELECTOR_KEYS, f"criterion {criterion_id}.outcome contains unsupported key '{key}'.")

    if verification in MACHINE_VERIFICATIONS:
        if verification in {"file_exists", "file_contains", "file_equals", "json_schema"}:
            _relative_path(criterion.get("path"), f"criterion {criterion_id}.path")
            if verification in {"file_contains", "file_equals"}:
                _require(isinstance(criterion.get("text"), str), f"criterion {criterion_id}.text must be a string.")
            if verification == "json_schema":
                _require(isinstance(criterion.get("schema"), dict), f"criterion {criterion_id}.schema must be an object.")
        elif verification == "command_succeeds":
            has_command = isinstance(criterion.get("command"), str) and bool(criterion["command"].strip())
            has_argv = isinstance(criterion.get("argv"), list) and bool(criterion["argv"]) and all(isinstance(item, str) and item for item in criterion["argv"])
            _require(has_command or has_argv, f"criterion {criterion_id} requires command or argv.")
        elif verification == "changed_paths":
            for name in ("min", "max"):
                if name in criterion:
                    _require(isinstance(criterion[name], int) and criterion[name] >= 0, f"criterion {criterion_id}.{name} must be a non-negative integer.")
            _require("min" in criterion or "max" in criterion, f"criterion {criterion_id} requires min or max.")
    return criterion_id


def validate_contract(contract: Any) -> dict[str, Any]:
    _require(isinstance(contract, dict), "Goal contract must be a JSON object.")
    _require(contract.get("schema_version") == SCHEMA_VERSION, f"Goal schema_version must be {SCHEMA_VERSION}.")
    goal_id = contract.get("goal_id")
    _require(isinstance(goal_id, str) and GOAL_ID_PATTERN.fullmatch(goal_id) is not None, "goal_id is invalid.")
    criteria = contract.get("success_criteria")
    _require(isinstance(criteria, list) and criteria, "success_criteria must be a non-empty array.")
    policy = contract.get("completion_policy", {})
    _require(isinstance(policy, dict), "completion_policy must be an object.")
    _require(policy.get("require_all", True) is True, "completion_policy.require_all must be true.")
    review = policy.get("review", "none")
    _require(review in {"none", "codex", "independent"}, "completion_policy.review is invalid.")
    user_acceptance = policy.get("user_acceptance", "not_required")
    _require(user_acceptance in {"not_required", "required"}, "completion_policy.user_acceptance is invalid.")
    platforms = policy.get("platforms", [])
    _require(isinstance(platforms, list) and all(item in {"macos", "windows"} for item in platforms), "completion_policy.platforms must contain only macos/windows.")
    stop_policy = contract.get("stop_policy", {})
    _require(isinstance(stop_policy, dict), "stop_policy must be an object.")
    max_attempts = stop_policy.get("max_attempts", 1)
    _require(isinstance(max_attempts, int) and not isinstance(max_attempts, bool) and max_attempts >= 1, "stop_policy.max_attempts must be a positive integer.")
    _require(stop_policy.get("on_blocked", "pause") == "pause", "stop_policy.on_blocked must be 'pause'.")

    ids: set[str] = set()
    has_required = False
    has_review = False
    has_acceptance = False
    for index, criterion in enumerate(criteria):
        criterion_id = _validate_criterion(criterion, index, platforms)
        _require(criterion_id not in ids, f"Duplicate criterion id: {criterion_id}.")
        ids.add(criterion_id)
        has_required = has_required or criterion["required"]
        has_review = has_review or criterion["required"] and criterion["verification"] == "review"
        has_acceptance = has_acceptance or criterion["required"] and criterion["verification"] == "user_acceptance"
    _require(has_required, "Goal contract must contain at least one required criterion.")
    for platform in platforms:
        _require(any(item.get("required") and item.get("platform") == platform for item in criteria), f"Platform {platform} requires at least one required platform criterion.")
    if review != "none":
        _require(has_review, "A non-none review policy requires a required review criterion.")
    if user_acceptance == "required":
        _require(has_acceptance, "A required user_acceptance policy requires a required user_acceptance criterion.")

    normalized = copy.deepcopy(contract)
    normalized.setdefault("completion_policy", {})
    normalized["completion_policy"].setdefault("require_all", True)
    normalized["completion_policy"].setdefault("review", "none")
    normalized["completion_policy"].setdefault("user_acceptance", "not_required")
    normalized["completion_policy"].setdefault("platforms", [])
    normalized.setdefault("stop_policy", {})
    normalized["stop_policy"].setdefault("max_attempts", 1)
    normalized["stop_policy"].setdefault("on_blocked", "pause")
    return normalized


def load_contract(path: Path) -> dict[str, Any]:
    return validate_contract(load_json(path))


def default_state_path(control_root: Path, goal_id: str) -> Path:
    return control_root / "goals" / f"{goal_id}.json"


def new_state(contract: dict[str, Any], contract_path: str | None = None) -> dict[str, Any]:
    contract = validate_contract(contract)
    criteria = {
        item["id"]: {
            "id": item["id"],
            "required": item["required"],
            "verification": item["verification"],
            **({"platform": item["platform"]} if item.get("platform") else {}),
            "status": "pending",
            "evidence": [],
            "updated_at": None,
        }
        for item in contract["success_criteria"]
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "goal_id": contract["goal_id"],
        "contract_sha256": json_hash(contract),
        "contract_path": contract_path,
        "status": "active",
        "attempts": 0,
        "criteria": criteria,
        "runs": [],
        "decisions": [],
        "history": [],
        "blocker": None,
        "close": None,
        "created_at": now(),
        "updated_at": now(),
    }


def load_state(path: Path, contract: dict[str, Any], contract_path: str | None = None) -> dict[str, Any]:
    contract = validate_contract(contract)
    if not path.exists():
        return new_state(contract, contract_path)
    state = load_json(path)
    _require(isinstance(state, dict), "Goal state must be a JSON object.")
    _require(state.get("schema_version") == SCHEMA_VERSION, f"Goal state schema_version must be {SCHEMA_VERSION}.")
    _require(state.get("goal_id") == contract["goal_id"], "Goal state goal_id does not match contract.")
    _require(state.get("contract_sha256") == json_hash(contract), "Goal contract changed; create a new Goal state or migrate it explicitly.")
    _require(state.get("status") in GOAL_STATUSES, "Goal state contains an invalid status.")
    expected_ids = {item["id"] for item in contract["success_criteria"]}
    actual_ids = set(state.get("criteria", {})) if isinstance(state.get("criteria"), dict) else set()
    _require(actual_ids == expected_ids, "Goal state criteria do not match the contract.")
    for criterion_id, item in state["criteria"].items():
        _require(isinstance(item, dict) and item.get("status") in CRITERION_STATUSES, f"Goal criterion {criterion_id} has an invalid status.")
    _require(isinstance(state.get("attempts"), int) and state["attempts"] >= 0, "Goal state attempts must be a non-negative integer.")
    _require(isinstance(state.get("runs"), list) and isinstance(state.get("decisions"), list) and isinstance(state.get("history"), list), "Goal state history fields must be arrays.")
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    with locked(path):
        write_json(path, state)


def ensure_can_start_run(state: dict[str, Any], contract: dict[str, Any]) -> None:
    _require(state["status"] == "active", f"Goal is {state['status']} and cannot start a Run.")
    maximum = contract.get("stop_policy", {}).get("max_attempts", 1)
    _require(state["attempts"] < maximum, "Goal reached its max_attempts and is closed as failed.")


def _criterion_selector(criterion: dict[str, Any]) -> dict[str, Any]:
    selector = criterion.get("outcome")
    if isinstance(selector, dict):
        return {key: value for key, value in selector.items() if key in SAFE_SELECTOR_KEYS}
    return {key: criterion[key] for key in SAFE_SELECTOR_KEYS if key in criterion and key != "type"}


def _outcome_matches(criterion: dict[str, Any], outcome: dict[str, Any]) -> bool:
    verification = criterion["verification"]
    if outcome.get("type") != verification:
        return False
    selector = _criterion_selector(criterion)
    expected = outcome.get("expected") if isinstance(outcome.get("expected"), dict) else {}
    for key, value in selector.items():
        actual = outcome.get(key, expected.get(key))
        if actual != value:
            return False
    return True


def _evidence(run_record: dict[str, Any], outcomes: list[dict[str, Any]]) -> list[str]:
    evidence: list[str] = []
    run_id = run_record.get("run_id")
    if isinstance(run_id, str) and run_id:
        evidence.append(f"run:{run_id}")
    output_path = run_record.get("output_path")
    if isinstance(output_path, str) and output_path:
        evidence.append(output_path)
    for outcome in outcomes:
        for key in ("path", "command"):
            value = outcome.get(key)
            if isinstance(value, str) and value and value not in evidence:
                evidence.append(value)
    return evidence[:12]


def _set_criterion(state: dict[str, Any], criterion_id: str, status: str, evidence: list[str], reason: str | None = None) -> None:
    item = state["criteria"][criterion_id]
    item["status"] = status
    item["evidence"] = list(dict.fromkeys(evidence))[:20]
    item["updated_at"] = now()
    if reason:
        item["reason"] = reason
    elif "reason" in item:
        item.pop("reason")


def _recompute(state: dict[str, Any], contract: dict[str, Any], fail_on_required_failure: bool = False) -> str:
    required = [item for item in state["criteria"].values() if item["required"]]
    if all(item["status"] in {"passed", "not_applicable"} for item in required):
        return "achieved"
    if fail_on_required_failure and any(item["status"] == "failed" for item in required):
        return "failed"
    maximum = contract.get("stop_policy", {}).get("max_attempts", 1)
    if state["attempts"] >= maximum:
        return "failed"
    return "active"


def _close_if_terminal(state: dict[str, Any], previous: str) -> None:
    if state["status"] in {"achieved", "failed", "blocked", "cancelled"} and previous != state["status"]:
        state["close"] = {"status": state["status"], "closed_at": now()}
    elif state["status"] == "active":
        state["close"] = None
    state["updated_at"] = now()


def record_run(state: dict[str, Any], contract: dict[str, Any], run_record: dict[str, Any]) -> dict[str, Any]:
    contract = validate_contract(contract)
    state = copy.deepcopy(load_state_from_value(state, contract))
    ensure_can_start_run(state, contract)
    run_id = run_record.get("run_id")
    _require(isinstance(run_id, str) and run_id, "Run record requires a run_id.")
    _require(run_record.get("status") in RUN_STATUSES, "Run record contains an invalid Run status.")
    _require(run_id not in {item.get("run_id") for item in state["runs"]}, f"Run {run_id} is already recorded for this Goal.")
    outcomes = run_record.get("outcome_results", [])
    _require(isinstance(outcomes, list), "Run outcome_results must be an array.")
    run_platform = run_record.get("host_platform")
    run_summary = {
        "run_id": run_id,
        "status": run_record.get("status"),
        "action": run_record.get("action"),
        "platform": run_platform,
        "output_path": run_record.get("output_path"),
        "recorded_at": now(),
    }
    state["attempts"] += 1
    state["runs"].append(run_summary)
    for criterion in contract["success_criteria"]:
        criterion_id = criterion["id"]
        current = state["criteria"][criterion_id]
        if criterion["verification"] in MANUAL_VERIFICATIONS or current["status"] in {"passed", "not_applicable"}:
            continue
        required_platform = criterion.get("platform")
        if required_platform and required_platform != run_platform:
            continue
        matches = [outcome for outcome in outcomes if isinstance(outcome, dict) and _outcome_matches(criterion, outcome)]
        if not matches:
            continue
        evidence = _evidence(run_record, matches)
        if run_record.get("status") == "completed" and all(outcome.get("passed") is True for outcome in matches):
            _set_criterion(state, criterion_id, "passed", evidence)
        elif any(outcome.get("passed") is False for outcome in matches):
            _set_criterion(state, criterion_id, "failed", evidence, "A matching Run outcome failed.")

    previous = state["status"]
    state["status"] = _recompute(state, contract)
    _close_if_terminal(state, previous)
    state["history"].append({"event": "run", "run_id": run_id, "status": state["status"], "at": now()})
    return state


def load_state_from_value(state: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(state, dict), "Goal state must be an object.")
    expected = new_state(contract)
    _require(state.get("goal_id") == expected["goal_id"], "Goal state goal_id does not match contract.")
    _require(state.get("contract_sha256") == expected["contract_sha256"], "Goal contract changed.")
    _require(state.get("status") in GOAL_STATUSES, "Goal state contains an invalid status.")
    _require(isinstance(state.get("criteria"), dict) and set(state["criteria"]) == set(expected["criteria"]), "Goal state criteria do not match contract.")
    for criterion_id, item in state["criteria"].items():
        _require(isinstance(item, dict) and item.get("status") in CRITERION_STATUSES, f"Goal criterion {criterion_id} has an invalid status.")
    return state


def apply_decision(state: dict[str, Any], contract: dict[str, Any], criterion_id: str, status: str, evidence: list[str], actor: str, reason: str | None = None) -> dict[str, Any]:
    contract = validate_contract(contract)
    state = copy.deepcopy(load_state_from_value(state, contract))
    _require(state["status"] in {"active", "blocked"}, f"Goal is {state['status']} and cannot accept a new decision.")
    _require(criterion_id in state["criteria"], f"Unknown criterion id: {criterion_id}.")
    _require(status in {"passed", "failed", "not_applicable"}, "Decision status must be passed, failed or not_applicable.")
    criterion = next(item for item in contract["success_criteria"] if item["id"] == criterion_id)
    _require(criterion["verification"] in MANUAL_VERIFICATIONS or status == "not_applicable", f"Criterion {criterion_id} requires a machine Run outcome.")
    _require(isinstance(actor, str) and actor.strip(), "Decision actor is required.")
    _require(isinstance(evidence, list) and all(isinstance(item, str) and item.strip() for item in evidence), "Decision evidence must be a list of non-empty paths or references.")
    _require(status == "failed" or evidence, "A passing or not_applicable decision requires evidence.")
    if status == "failed":
        _require(bool(reason and reason.strip()), "A failed decision requires a reason.")
    if status == "not_applicable":
        _require(bool(reason and reason.strip()), "A not_applicable decision requires a reason.")
    _set_criterion(state, criterion_id, status, evidence, reason)
    decision = {"criterion_id": criterion_id, "status": status, "evidence": evidence[:20], "actor": actor, "reason": reason, "at": now()}
    state["decisions"].append(decision)
    previous = state["status"]
    state["status"] = _recompute(state, contract, fail_on_required_failure=True)
    _close_if_terminal(state, previous)
    state["history"].append({"event": "decision", "criterion_id": criterion_id, "status": state["status"], "at": now()})
    return state


def block_goal(state: dict[str, Any], contract: dict[str, Any], reason: str, owner: str, unlock_condition: str, evidence: list[str]) -> dict[str, Any]:
    contract = validate_contract(contract)
    state = copy.deepcopy(load_state_from_value(state, contract))
    _require(state["status"] == "active", f"Goal is {state['status']} and cannot be blocked.")
    _require(all(isinstance(value, str) and value.strip() for value in (reason, owner, unlock_condition)), "A blocker requires reason, owner and unlock_condition.")
    _require(isinstance(evidence, list) and evidence and all(isinstance(item, str) and item.strip() for item in evidence), "Blocker evidence must be a non-empty list.")
    previous = state["status"]
    state["status"] = "blocked"
    state["blocker"] = {"reason": reason, "owner": owner, "unlock_condition": unlock_condition, "evidence": evidence[:20], "created_at": now()}
    _close_if_terminal(state, previous)
    state["history"].append({"event": "blocked", "at": now()})
    return state


def unblock_goal(state: dict[str, Any], contract: dict[str, Any], evidence: list[str]) -> dict[str, Any]:
    contract = validate_contract(contract)
    state = copy.deepcopy(load_state_from_value(state, contract))
    _require(state["status"] == "blocked", f"Goal is {state['status']} and cannot be unblocked.")
    _require(isinstance(evidence, list) and evidence and all(isinstance(item, str) and item.strip() for item in evidence), "Unblocking requires evidence.")
    previous = state["status"]
    state["status"] = "active"
    state["blocker"]["resolved_at"] = now()
    state["blocker"]["resolution_evidence"] = evidence[:20]
    state["close"] = None
    state["updated_at"] = now()
    state["history"].append({"event": "unblocked", "evidence": evidence[:20], "at": now()})
    _require(previous == "blocked", "Goal was not blocked.")
    return state


def cancel_goal(state: dict[str, Any], contract: dict[str, Any], actor: str, reason: str) -> dict[str, Any]:
    contract = validate_contract(contract)
    state = copy.deepcopy(load_state_from_value(state, contract))
    _require(state["status"] in {"active", "blocked"}, f"Goal is {state['status']} and cannot be cancelled.")
    _require(isinstance(actor, str) and actor.strip() and isinstance(reason, str) and reason.strip(), "Cancellation requires actor and reason.")
    previous = state["status"]
    state["status"] = "cancelled"
    state["history"].append({"event": "cancelled", "actor": actor, "reason": reason, "at": now()})
    _close_if_terminal(state, previous)
    return state


def state_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal_id": state["goal_id"],
        "status": state["status"],
        "attempts": state["attempts"],
        "criteria": {
            criterion_id: {key: value for key, value in item.items() if key in {"id", "required", "verification", "platform", "status", "evidence", "reason"}}
            for criterion_id, item in state["criteria"].items()
        },
        "blocker": state.get("blocker"),
        "close": state.get("close"),
        "updated_at": state.get("updated_at"),
    }


def _project_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    _require(not candidate.is_absolute() and ".." not in candidate.parts, "Path must be project-relative and contain no '..'.")
    resolved = (root / candidate).resolve()
    _require(resolved == root.resolve() or root.resolve() in resolved.parents, "Path must stay inside the project root.")
    return resolved


def _load_for_cli(args: argparse.Namespace) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    root = Path(args.project_root).resolve()
    contract_path = _project_path(root, args.contract)
    contract = load_contract(contract_path)
    control_root = root / ".ai-collaboration"
    state_path = _project_path(root, args.state) if args.state else default_state_path(control_root, contract["goal_id"])
    state = load_state(state_path, contract, str(contract_path.relative_to(root)))
    return root, contract, state_path, state


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(skill_project_root()))
    subparsers = parser.add_subparsers(dest="action", required=True)
    for name in ("validate", "show", "record-run", "decide", "block", "unblock", "cancel"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--contract", required=True)
        sub.add_argument("--state")
    subparsers.choices["record-run"].add_argument("--run-record", required=True)
    decide = subparsers.choices["decide"]
    decide.add_argument("--criterion-id", required=True)
    decide.add_argument("--status", required=True, choices=("passed", "failed", "not_applicable"))
    decide.add_argument("--evidence", action="append", default=[])
    decide.add_argument("--actor", required=True)
    decide.add_argument("--reason")
    block = subparsers.choices["block"]
    block.add_argument("--reason", required=True)
    block.add_argument("--owner", required=True)
    block.add_argument("--unlock-condition", required=True)
    block.add_argument("--evidence", action="append", default=[])
    subparsers.choices["unblock"].add_argument("--evidence", action="append", default=[])
    cancel = subparsers.choices["cancel"]
    cancel.add_argument("--actor", required=True)
    cancel.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "validate":
            root = Path(args.project_root).resolve()
            contract = load_contract(_project_path(root, args.contract))
            print(json.dumps({"goal_id": contract["goal_id"], "valid": True}, ensure_ascii=False, indent=2))
            return 0
        _root, contract, state_path, state = _load_for_cli(args)
        if args.action == "show":
            print(json.dumps(state_summary(state), ensure_ascii=False, indent=2))
            return 0
        if args.action == "record-run":
            run_record = load_json(_project_path(_root, args.run_record))
            state = record_run(state, contract, run_record)
        elif args.action == "decide":
            state = apply_decision(state, contract, args.criterion_id, args.status, args.evidence, args.actor, args.reason)
        elif args.action == "block":
            state = block_goal(state, contract, args.reason, args.owner, args.unlock_condition, args.evidence)
        elif args.action == "unblock":
            state = unblock_goal(state, contract, args.evidence)
        elif args.action == "cancel":
            state = cancel_goal(state, contract, args.actor, args.reason)
        save_state(state_path, state)
        print(json.dumps(state_summary(state), ensure_ascii=False, indent=2))
        return 0
    except (GoalError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
