#!/usr/bin/env python3
"""Regression tests for portable profile diagnostics and Keychain handling."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


DOCTOR_SCRIPT = Path(__file__).with_name("doctor.py")
DOCTOR_SPEC = importlib.util.spec_from_file_location("doctor", DOCTOR_SCRIPT)
assert DOCTOR_SPEC and DOCTOR_SPEC.loader
doctor = importlib.util.module_from_spec(DOCTOR_SPEC)
DOCTOR_SPEC.loader.exec_module(doctor)

COLLABORATE_SCRIPT = Path(__file__).with_name("collaborate.py")
COLLABORATE_SPEC = importlib.util.spec_from_file_location("collaborate", COLLABORATE_SCRIPT)
assert COLLABORATE_SPEC and COLLABORATE_SPEC.loader
collaborate = importlib.util.module_from_spec(COLLABORATE_SPEC)
COLLABORATE_SPEC.loader.exec_module(collaborate)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        profile_file = root / "providers.local.json"
        profile_file.write_text(json.dumps({"provider_a": {"config_dir": str(root), "launcher": "claude", "auth_token_keychain_service": "test-service"}}), encoding="utf-8")
        original = doctor.CONTROL_ROOT
        doctor.CONTROL_ROOT = root
        try:
            problems = doctor.check("provider_a")
        finally:
            doctor.CONTROL_ROOT = original
        if collaborate.host_platform() == "macos":
            assert problems
        else:
            assert any("Keychain authentication is unavailable" in item for item in problems)
            profile = {"config_dir": str(root), "auth_token_keychain_service": "test-service", "environment": {}}
            assert "Keychain authentication is unavailable" in (collaborate.profile_problem(profile) or "")
            try:
                collaborate.provider_environment(profile)
            except collaborate.CollaborationError as exc:
                assert "Keychain authentication is unavailable" in str(exc)
            else:
                raise AssertionError("Non-macOS Keychain profile must be rejected before invocation.")
    print("doctor tests passed")


if __name__ == "__main__":
    main()
