#!/usr/bin/env python3
"""Regression tests for persistent fair provider routing."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("provider_routing.py")
SPEC = importlib.util.spec_from_file_location("provider_routing", SCRIPT)
assert SPEC and SPEC.loader
routing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(routing)


def main() -> None:
    metrics = routing.default_metrics()
    first, first_info = routing.choose_provider(metrics, ["mimo", "deepseek"], "code", "execute")
    second, second_info = routing.choose_provider(metrics, ["mimo", "deepseek"], "code", "execute")
    assert first == "deepseek" and second == "mimo"
    assert first_info["basis"] == second_info["basis"] == "starter_policy_coding_execute_rotation"
    for _ in range(3):
        routing.append_event(metrics, {"provider": "mimo", "task_type": "code", "mode": "execute", "status": "completed", "quality_score": 4.7, "duration_seconds": 30})
        routing.append_event(metrics, {"provider": "deepseek", "task_type": "code", "mode": "execute", "status": "completed", "quality_score": 3.8, "duration_seconds": 10})
    selected, info = routing.choose_provider(metrics, ["mimo", "deepseek"], "code", "execute")
    assert selected == "deepseek" and info["basis"] == "starter_policy_coding_execute_rotation"
    text, text_info = routing.choose_provider(metrics, ["mimo", "deepseek"], "research", "analyze")
    assert text == "deepseek" and text_info["basis"] == "starter_policy_text_reasoning_rotation"

    fixed, fixed_info = routing.choose_provider(routing.default_metrics(), ["mimo", "deepseek"], "research", "analyze", {"default": {"strategy": "fixed", "provider": "mimo"}, "task_overrides": {}})
    assert fixed == "mimo" and fixed_info["basis"] == "configured_fixed"
    try:
        routing.choose_provider(routing.default_metrics(), ["deepseek"], "research", "analyze", {"default": {"strategy": "fixed", "provider": "mimo"}, "task_overrides": {}})
    except routing.RoutingError as exc:
        assert exc.code == "fixed_provider_unavailable"
    else:
        raise AssertionError("fixed unavailable provider must fail closed")

    weighted_metrics = routing.default_metrics()
    weighted_config = {"default": {"strategy": "weighted_round_robin", "weights": {"deepseek": 2, "mimo": 1}}, "task_overrides": {}}
    sequence = [routing.choose_provider(weighted_metrics, ["deepseek", "mimo"], "code", "execute", weighted_config)[0] for _ in range(6)]
    assert sequence.count("deepseek") == 4 and sequence.count("mimo") == 2
    assert routing.choose_provider(routing.default_metrics(), ["deepseek", "mimo"], "code", "execute", weighted_config)[0] == sequence[0]
    state_keys = [key for key in weighted_metrics["routing_state"] if key.startswith("weighted_round_robin|")]
    routing.choose_provider(weighted_metrics, ["deepseek"], "code", "execute", weighted_config)
    assert len(weighted_metrics["routing_state"]) == 2 and len(state_keys) == 1

    corrupted = routing.default_metrics()
    corrupted["events"].append({"provider": "deepseek", "status": "completed"})
    routing.choose_provider(corrupted, ["deepseek", "mimo"], "code", "execute", weighted_config)
    corrupted_state_key = next(iter(corrupted["routing_state"]))
    corrupted["routing_state"][corrupted_state_key]["current_weights"] = "not-a-map"
    selected, info = routing.choose_provider(corrupted, ["deepseek", "mimo"], "code", "execute", weighted_config)
    assert selected == "deepseek" and info["state_rebuilt"] and len(corrupted["events"]) == 1

    cleaned = routing.default_metrics()
    routing.append_event(cleaned, {"provider": "mimo", "task_type": "code", "mode": "execute", "status": "completed", "prompt": "must not persist"})
    assert "prompt" not in cleaned["events"][0]
    print("provider-routing tests passed")


if __name__ == "__main__":
    main()
