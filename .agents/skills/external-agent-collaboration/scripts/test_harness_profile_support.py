#!/usr/bin/env python3
"""Regression tests for non-secret Antigravity profile and trust handling."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import harness_profile_support as profiles


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        profile = {"harness": "antigravity", "launcher": "agy", "mode": "plan", "effort": "medium"}
        (root / "harness-profiles.local.json").write_text(json.dumps({"schema_version": 1, "profiles": {"readonly": profile}}), encoding="utf-8")
        loaded = profiles.load_profiles(root)
        assert loaded["readonly"] == profile and not profiles.trusted(root, "readonly", profile)
        (root / "trusted-harnesses.local.json").write_text(json.dumps({"schema_version": 1, "profiles": {"readonly": {"approved": True, "profile_fingerprint": profiles.profile_fingerprint(profile)}}}), encoding="utf-8")
        assert profiles.trusted(root, "readonly", profile)
        (root / "harness-profiles.local.json").write_text(json.dumps({"profiles": {"bad": {"harness": "antigravity", "mode": "plan", "api_token": "not-allowed"}}}), encoding="utf-8")
        try:
            profiles.load_profiles(root)
        except profiles.HarnessProfileError as exc:
            assert "credentials" in str(exc)
        else:
            raise AssertionError("credential field must be rejected")
    print("harness-profile-support tests passed")


if __name__ == "__main__":
    main()
