#!/usr/bin/env python3
"""Regression tests for configurable routing loading and validation."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import profile_support


PROVIDERS = {"deepseek", "mimo"}
PORTABLE = {
    "config_dir_relative_to_home": ".claude-provider",
    "launcher": "claude",
    "environment": {"ANTHROPIC_BASE_URL": "https://provider.example/anthropic"},
}


def expect_error(value, message: str) -> None:
    try:
        value()
    except profile_support.ProfileConfigError as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError("invalid routing configuration was accepted")


def main() -> None:
    default = profile_support.validate_routing_policy(profile_support.default_routing(), PROVIDERS)
    assert default["default"]["strategy"] == "fair_round_robin"

    with tempfile.TemporaryDirectory(prefix="routing-config-test-") as directory:
        control = Path(directory)
        shared = {
            "schema_version": 1,
            "providers": {"deepseek": copy.deepcopy(PORTABLE), "mimo": copy.deepcopy(PORTABLE)},
            "routing": {
                "default": {"strategy": "fair_round_robin"},
                "task_overrides": {"code:execute": {"strategy": "weighted_round_robin", "weights": {"deepseek": 2, "mimo": 1}}},
                "platform_overrides": {"windows": {"default": {"strategy": "fixed", "provider": "mimo"}}},
            },
        }
        (control / "providers.shared.json").write_text(json.dumps(shared), encoding="utf-8")
        (control / "providers.local.json").write_text(json.dumps({"routing": {"default": {"strategy": "fixed", "provider": "deepseek"}}}), encoding="utf-8")
        (control / "providers.local.macos.json").write_text(json.dumps({"routing": {"task_overrides": {"data:analyze": {"strategy": "fixed", "provider": "mimo"}}}}), encoding="utf-8")
        (control / "providers.local.windows.json").write_text(json.dumps({"routing": {"default": {"strategy": "fixed", "provider": "mimo"}}}), encoding="utf-8")
        macos = profile_support.load_routing(control, PROVIDERS, "macos")
        assert macos["default"] == {"strategy": "fixed", "provider": "deepseek"}
        assert macos["task_overrides"]["code:execute"]["weights"] == {"deepseek": 2, "mimo": 1}
        assert macos["task_overrides"]["data:analyze"] == {"strategy": "fixed", "provider": "mimo"}
        windows = profile_support.load_routing(control, PROVIDERS, "windows")
        assert windows["default"] == {"strategy": "fixed", "provider": "mimo"}

        profiles_with_routing = profile_support.load_profiles(control)
        shared_without_routing = copy.deepcopy(shared)
        shared_without_routing.pop("routing")
        (control / "providers.shared.json").write_text(json.dumps(shared_without_routing), encoding="utf-8")
        profiles_without_routing = profile_support.load_profiles(control)
        assert profiles_with_routing == profiles_without_routing, "routing must not enter provider profile identity"

        no_routing = profile_support.load_routing(control / "missing", PROVIDERS, "macos")
        assert no_routing["default"]["strategy"] == "fair_round_robin"

        expect_error(lambda: profile_support.validate_routing_policy({"schema_version": 1, "default": {"strategy": "unknown"}}, PROVIDERS), "strategy")
        expect_error(lambda: profile_support.validate_routing_policy({"schema_version": 1, "default": {"strategy": "fixed", "provider": "other"}}, PROVIDERS), "routing_provider_unknown")
        expect_error(lambda: profile_support.validate_routing_policy({"schema_version": 1, "default": {"strategy": "weighted_round_robin", "weights": {"mimo": 0}}}, PROVIDERS), "integer")
        expect_error(lambda: profile_support.provider_map({"routing": {}, "mimo": {}}, "legacy.json"), "wrap providers")

    print("routing-config tests passed")


if __name__ == "__main__":
    main()
