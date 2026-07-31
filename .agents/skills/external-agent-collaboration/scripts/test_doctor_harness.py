#!/usr/bin/env python3
"""Regression test for no-request Antigravity prerequisite diagnostics."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import collaborate
import doctor_harness
from harness_profile_support import profile_fingerprint


def main() -> None:
    original = collaborate.CONTROL_ROOT
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        profile = {"harness": "antigravity", "launcher": "python3", "mode": "plan"}
        (root / "harness-profiles.local.json").write_text(json.dumps({"profiles": {"readonly": profile}}), encoding="utf-8")
        (root / "trusted-harnesses.local.json").write_text(json.dumps({"profiles": {"readonly": {"approved": True, "profile_fingerprint": profile_fingerprint(profile)}}}), encoding="utf-8")
        collaborate.CONTROL_ROOT = root
        try:
            payload = doctor_harness.check("readonly")
            assert payload["ok"] is True and payload["interactive_authentication"] == "not_checked_without_a_real_request"
        finally:
            collaborate.CONTROL_ROOT = original
    print("doctor-harness tests passed")


if __name__ == "__main__":
    main()
