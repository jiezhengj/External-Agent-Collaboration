#!/usr/bin/env python3
"""Regression tests for shared profiles and direct-token platform overlays."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

import profile_support


def main() -> None:
    portable = {
        "config_dir_relative_to_home": ".claude-mimo",
        "launcher": "claude",
        "environment": {"ANTHROPIC_BASE_URL": "https://provider.example/anthropic"},
    }
    home = Path("C:/Users/example")
    assert profile_support.resolve_profile(portable, platform="windows", home=home)["config_dir"] == str(PureWindowsPath(str(home)) / ".claude-mimo")
    assert profile_support.resolve_profile(portable, platform="macos", home=PurePosixPath("/Users/example"))["config_dir"] == "/Users/example/.claude-mimo"

    with tempfile.TemporaryDirectory() as directory:
        control = Path(directory)
        shared = {"schema_version": 1, "providers": {"mimo": portable}}
        local = {"schema_version": 1, "providers": {"mimo": {"auth_token": "generic-token"}}}
        windows = {"schema_version": 1, "providers": {"mimo": {"auth_token": "windows-token", "config_dir": "C:/Users/example/.claude-mimo"}}}
        macos = {"schema_version": 1, "providers": {"mimo": {"auth_token": "macos-token", "config_dir": "/Users/example/.claude-mimo"}}}
        (control / "providers.shared.json").write_text(json.dumps(shared), encoding="utf-8")
        (control / "providers.local.json").write_text(json.dumps(local), encoding="utf-8")
        (control / "providers.local.windows.json").write_text(json.dumps(windows), encoding="utf-8")
        (control / "providers.local.macos.json").write_text(json.dumps(macos), encoding="utf-8")
        original_platform = profile_support.host_platform
        try:
            profile_support.host_platform = lambda: "windows"
            resolved = profile_support.load_profiles(control)["mimo"]
            assert resolved["launcher"] == "claude"
            assert resolved["auth_token"] == "windows-token"
            assert resolved["config_dir"] == "C:/Users/example/.claude-mimo"
            profile_support.host_platform = lambda: "macos"
            resolved = profile_support.load_profiles(control)["mimo"]
            assert resolved["auth_token"] == "macos-token"
            assert resolved["config_dir"] == "/Users/example/.claude-mimo"
        finally:
            profile_support.host_platform = original_platform

        shared["providers"]["mimo"]["auth_token"] = "forbidden"
        (control / "providers.shared.json").write_text(json.dumps(shared), encoding="utf-8")
        try:
            profile_support.load_profiles(control)
        except profile_support.ProfileConfigError as exc:
            assert "auth_token" in str(exc)
        else:
            raise AssertionError("Shared profile containing a token must be rejected.")
    print("profile-support tests passed")


if __name__ == "__main__":
    main()
