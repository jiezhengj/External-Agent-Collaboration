#!/usr/bin/env python3
"""Deterministic, configurable provider routing for externally eligible work."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from harness_state import state_identity
from platform_support import host_platform


class RoutingError(ValueError):
    """Raised when a valid routing policy cannot select an eligible provider."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def metric_key(task_type: str, mode: str) -> str:
    return f"{task_type}:{mode}"


def default_metrics() -> dict[str, Any]:
    return {"schema_version": 2, "round_robin_cursor": {}, "routing_state": {}, "events": []}


def valid_metrics(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return default_metrics()
    version = data.get("schema_version", 1)
    data["schema_version"] = max(version, 2) if isinstance(version, int) and not isinstance(version, bool) else 2
    if not isinstance(data.get("round_robin_cursor"), dict):
        data["round_robin_cursor"] = {}
    if not isinstance(data.get("routing_state"), dict):
        data["routing_state"] = {}
        data["_routing_state_rebuilt"] = True
    return data


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _default_config() -> dict[str, Any]:
    return {"schema_version": 1, "default": {"strategy": "fair_round_robin"}, "task_overrides": {}}


def resolve_policy(config: dict[str, Any] | None, task_type: str, mode: str) -> tuple[dict[str, Any], str]:
    """Resolve a task override before the default, with fair compatibility fallback."""
    if config is None:
        return {"strategy": "fair_round_robin"}, "compatibility_default"
    if not isinstance(config, dict):
        config = _default_config()
    overrides = config.get("task_overrides", {})
    key = metric_key(task_type, mode)
    if isinstance(overrides, dict) and isinstance(overrides.get(key), dict):
        return dict(overrides[key]), "task_override"
    default = config.get("default")
    if isinstance(default, dict):
        return dict(default), "default"
    return {"strategy": "fair_round_robin"}, "compatibility_default"


def _candidate_list(candidates: list[str]) -> list[str]:
    ordered = sorted({candidate for candidate in candidates if isinstance(candidate, str) and candidate})
    if not ordered:
        raise RoutingError("routing_no_healthy_candidate", "No provider candidates available.")
    return ordered


def _state_key(strategy: str, task_key: str, policy: dict[str, Any], candidates: list[str]) -> str:
    candidate_hash = _digest(candidates)
    if strategy == "fair_round_robin":
        return f"fair_round_robin|{task_key}|{candidate_hash}"
    return f"{strategy}|{task_key}|{_digest(policy)}|{candidate_hash}"


def _route_info(strategy: str, task_key: str, source: str, candidates: list[str], basis: str, state_key: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "basis": basis,
        "strategy": strategy,
        "policy_source": source,
        "task_key": task_key,
        "candidate_count": len(candidates),
    }
    if state_key is not None:
        result["state_key"] = state_key
    return result


def matching_events(data: dict[str, Any], provider: str, task_type: str, mode: str) -> list[dict[str, Any]]:
    return [
        event for event in data["events"]
        if isinstance(event, dict)
        and event.get("provider") == provider
        and event.get("task_type") == task_type
        and event.get("mode") == mode
        and event.get("status") in {"completed", "failed", "needs_review"}
    ]


def quality_score(events: list[dict[str, Any]]) -> float | None:
    scored = [event["quality_score"] for event in events if isinstance(event.get("quality_score"), (int, float))]
    if not scored:
        return None
    return sum(float(score) for score in scored) / len(scored)


def completed_rate(events: list[dict[str, Any]]) -> float:
    return sum(event.get("status") == "completed" for event in events) / len(events) if events else 0.0


def average_duration(events: list[dict[str, Any]]) -> float | None:
    values = [event["duration_seconds"] for event in events if isinstance(event.get("duration_seconds"), (int, float))]
    return sum(float(value) for value in values) / len(values) if values else None


def rotation_basis(task_type: str, mode: str) -> str:
    if task_type == "code" and mode == "execute":
        return "starter_policy_coding_execute_rotation"
    if task_type in {"code", "document", "research", "planning"}:
        return "starter_policy_text_reasoning_rotation"
    return "starter_policy_fair_rotation"


def choose_fair(metrics: dict[str, Any], candidates: list[str], task_type: str, mode: str, source: str = "compatibility_default") -> tuple[str, dict[str, Any]]:
    ordered = _candidate_list(candidates)
    key = metric_key(task_type, mode)
    metrics = valid_metrics(metrics)
    state = metrics.setdefault("routing_state", {})
    state_key = _state_key("fair_round_robin", key, {"strategy": "fair_round_robin"}, ordered)
    entry = state.get(state_key)
    if isinstance(entry, dict) and isinstance(entry.get("cursor"), int) and not isinstance(entry.get("cursor"), bool):
        cursor = entry["cursor"]
    elif not state and isinstance(metrics.get("round_robin_cursor", {}).get(key), int):
        cursor = int(metrics["round_robin_cursor"][key])
    else:
        cursor = 0
    selected = ordered[int(cursor) % len(ordered)]
    next_cursor = int(cursor) + 1
    state[state_key] = {"cursor": next_cursor}
    metrics["round_robin_cursor"][key] = next_cursor
    basis = rotation_basis(task_type, mode) if source == "compatibility_default" else "configured_default_fair_rotation" if source == "default" else "configured_task_fair_rotation"
    info = _route_info("fair_round_robin", key, source, ordered, basis, state_key)
    if metrics.pop("_routing_state_rebuilt", False):
        info["state_rebuilt"] = True
    return selected, info


def choose_fixed(candidates: list[str], policy: dict[str, Any], task_type: str, mode: str, source: str) -> tuple[str, dict[str, Any]]:
    ordered = _candidate_list(candidates)
    provider = policy.get("provider")
    if provider not in ordered:
        raise RoutingError("fixed_provider_unavailable", f"Fixed provider '{provider}' is not currently healthy and ready.")
    return provider, _route_info("fixed", metric_key(task_type, mode), source, ordered, "configured_fixed")


def choose_weighted(metrics: dict[str, Any], candidates: list[str], policy: dict[str, Any], task_type: str, mode: str, source: str) -> tuple[str, dict[str, Any]]:
    weights = policy.get("weights")
    if not isinstance(weights, dict):
        raise RoutingError("routing_config_invalid", "weighted_round_robin requires weights.")
    ordered = [candidate for candidate in _candidate_list(candidates) if candidate in weights]
    if not ordered:
        raise RoutingError("routing_no_healthy_candidate", "No weighted provider is currently healthy and ready.")
    metrics = valid_metrics(metrics)
    key = metric_key(task_type, mode)
    normalized_weights = {candidate: int(weights[candidate]) for candidate in ordered}
    normalized_policy = {"strategy": "weighted_round_robin", "weights": normalized_weights}
    state_key = _state_key("weighted_round_robin", key, normalized_policy, ordered)
    state = metrics.setdefault("routing_state", {})
    entry = state.get(state_key)
    rebuilt = False
    current: dict[str, int]
    if isinstance(entry, dict) and isinstance(entry.get("current_weights"), dict) and all(isinstance(value, int) and not isinstance(value, bool) for value in entry["current_weights"].values()):
        current = {candidate: int(entry["current_weights"].get(candidate, 0)) for candidate in ordered}
    else:
        current = {candidate: 0 for candidate in ordered}
        rebuilt = bool(entry is not None or metrics.pop("_routing_state_rebuilt", False))
    total = sum(normalized_weights.values())
    for candidate in ordered:
        current[candidate] += normalized_weights[candidate]
    selected = max(ordered, key=lambda candidate: (current[candidate], -ordered.index(candidate)))
    current[selected] -= total
    state[state_key] = {"current_weights": current}
    info = _route_info("weighted_round_robin", key, source, ordered, "configured_weighted_rotation", state_key)
    info["selected_weight"] = normalized_weights[selected]
    if rebuilt:
        info["state_rebuilt"] = True
    return selected, info


def choose_provider(metrics: dict[str, Any], candidates: list[str], task_type: str, mode: str, routing_config: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    policy, source = resolve_policy(routing_config, task_type, mode)
    strategy = policy.get("strategy", "fair_round_robin")
    if strategy == "fixed":
        return choose_fixed(candidates, policy, task_type, mode, source)
    if strategy == "weighted_round_robin":
        return choose_weighted(metrics, candidates, policy, task_type, mode, source)
    if strategy != "fair_round_robin":
        raise RoutingError("routing_config_invalid", f"Unsupported routing strategy: {strategy}")
    return choose_fair(metrics, candidates, task_type, mode, source)


def append_event(metrics: dict[str, Any], event: dict[str, Any]) -> None:
    allowed = {
        "run_id", "timestamp", "provider", "model_profile", "task_type", "mode",
        "risk", "status", "duration_seconds", "tool_refusal", "quality_score",
        "user_adopted", "rework_count", "route_basis", "cost_usd", "input_bytes", "handoff_bytes", "result_bytes", "return_bytes", "return_mode", "batch_status", "sample_passed", "harness", "harness_profile", "state_identity",
    }
    stored = {key: value for key, value in event.items() if key in allowed and value is not None}
    stored.setdefault("harness", "claude_code")
    stored.setdefault("harness_profile", str(stored.get("model_profile") or stored.get("provider") or "unknown"))
    stored.setdefault("state_identity", state_identity(str(stored["harness"]), str(stored["harness_profile"]), host_platform()))
    metrics["events"].append(stored)
