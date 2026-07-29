#!/usr/bin/env python3
"""Regression tests for local provider egress approval records."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("collaborate.py")
SPEC = importlib.util.spec_from_file_location("collaborate", SCRIPT)
assert SPEC and SPEC.loader
collaborate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collaborate)


def main() -> None:
    profile = {
        "config_dir": "/isolated/provider", "launcher": "claude",
        "auth_token": "must-not-affect-fingerprint",
        "environment": {"ANTHROPIC_BASE_URL": "https://provider.example/anthropic", "ANTHROPIC_MODEL": "model-a", "API_KEY": "must-not-affect-fingerprint"},
    }
    fingerprint = collaborate.profile_fingerprint(profile)
    changed_secret = {**profile, "auth_token": "changed"}
    changed_environment_secret = {**profile, "environment": {**profile["environment"], "API_KEY": "changed"}}
    assert collaborate.profile_fingerprint(changed_secret) == fingerprint
    assert collaborate.profile_fingerprint(changed_environment_secret) == fingerprint
    trust = {"schema_version": 1, "providers": {"provider_a": {"approved": True, "profile_fingerprint": fingerprint}}}
    assert collaborate.provider_is_trusted("provider_a", profile, trust)
    changed_model = {**profile, "environment": {**profile["environment"], "ANTHROPIC_MODEL": "model-b"}}
    assert not collaborate.provider_is_trusted("provider_a", changed_model, trust)
    assert collaborate.trusted_profiles({"provider_a": profile, "provider_b": profile}, trust) == {"provider_a": profile}
    with tempfile.TemporaryDirectory() as directory:
        original = collaborate.TRUST_FILE
        collaborate.TRUST_FILE = Path(directory) / "trusted-providers.local.json"
        try:
            assert collaborate.trust_registry() == {"schema_version": 1, "providers": {}}
        finally:
            collaborate.TRUST_FILE = original
    print("provider-trust tests passed")


if __name__ == "__main__":
    main()
