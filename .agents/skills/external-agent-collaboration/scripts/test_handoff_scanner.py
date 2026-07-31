#!/usr/bin/env python3
"""Ensure the runner's final egress scanner is separate from classification."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("collaborate.py")
SPEC = importlib.util.spec_from_file_location("collaborate", SCRIPT)
assert SPEC and SPEC.loader
collaborate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collaborate)
FAKE_TOKEN = "sk-" + "test_value_" * 3


def blocked(text: str, expected: str) -> None:
    try:
        collaborate.validate_handoff_sensitivity(text)
    except collaborate.CollaborationError as exc:
        message = str(exc)
        assert expected in message
        assert "sk-" not in message
    else:
        raise AssertionError("expected handoff scanner to block")


def main() -> None:
    collaborate.validate_handoff_sensitivity("Safety policy: do not send tokens or .env contents.")
    blocked("API_KEY=" + FAKE_TOKEN, "credential")
    blocked("Please review this attached .env file.", "requires redaction")
    print("handoff-scanner tests passed")


if __name__ == "__main__":
    main()
