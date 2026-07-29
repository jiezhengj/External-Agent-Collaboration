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
    cleaned = routing.default_metrics()
    routing.append_event(cleaned, {"provider": "mimo", "task_type": "code", "mode": "execute", "status": "completed", "prompt": "must not persist"})
    assert "prompt" not in cleaned["events"][0]
    print("provider-routing tests passed")


if __name__ == "__main__":
    main()
