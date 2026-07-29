#!/usr/bin/env python3
"""Privacy-preserving provider routing based on locally observed outcomes."""

from __future__ import annotations

from typing import Any


MIN_QUALITY_SAMPLES = 3


def metric_key(task_type: str, mode: str) -> str:
    return f"{task_type}:{mode}"


def default_metrics() -> dict[str, Any]:
    return {"schema_version": 1, "round_robin_cursor": {}, "events": []}


def valid_metrics(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return default_metrics()
    data.setdefault("schema_version", 1)
    data.setdefault("round_robin_cursor", {})
    return data


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


def choose_provider(metrics: dict[str, Any], candidates: list[str], task_type: str, mode: str) -> tuple[str, dict[str, Any]]:
    if not candidates:
        raise ValueError("No provider candidates available.")
    key = metric_key(task_type, mode)
    facts = {provider: matching_events(metrics, provider, task_type, mode) for provider in candidates}
    qualified = [provider for provider in candidates if len(facts[provider]) >= MIN_QUALITY_SAMPLES]
    if qualified:
        # Quality is primary; verified completion and speed only break ties. Unknown quality
        # is intentionally not treated as a positive score.
        ranked = sorted(
            qualified,
            key=lambda provider: (
                -(quality_score(facts[provider]) if quality_score(facts[provider]) is not None else -1.0),
                -completed_rate(facts[provider]),
                average_duration(facts[provider]) if average_duration(facts[provider]) is not None else float("inf"),
                provider,
            ),
        )
        selected = ranked[0]
        return selected, {
            "basis": "observed_metrics",
            "task_key": key,
            "sample_counts": {provider: len(facts[provider]) for provider in candidates},
            "selected_quality_score": quality_score(facts[selected]),
            "selected_completion_rate": completed_rate(facts[selected]),
        }

    cursor = metrics.setdefault("round_robin_cursor", {}).get(key, 0)
    ordered = sorted(candidates)
    selected = ordered[int(cursor) % len(ordered)]
    metrics["round_robin_cursor"][key] = int(cursor) + 1
    return selected, {
        "basis": "cold_start_round_robin",
        "task_key": key,
        "sample_counts": {provider: len(facts[provider]) for provider in candidates},
    }


def append_event(metrics: dict[str, Any], event: dict[str, Any]) -> None:
    allowed = {
        "run_id", "timestamp", "provider", "model_profile", "task_type", "mode",
        "risk", "status", "duration_seconds", "tool_refusal", "quality_score",
        "user_adopted", "rework_count", "route_basis", "cost_usd", "input_bytes", "handoff_bytes", "result_bytes", "return_bytes", "return_mode", "batch_status", "sample_passed",
    }
    metrics["events"].append({key: value for key, value in event.items() if key in allowed and value is not None})
