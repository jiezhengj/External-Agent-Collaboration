#!/usr/bin/env python3
"""Regression tests for session fork registration and durable topic references."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("collaborate.py")
SPEC = importlib.util.spec_from_file_location("collaborate", SCRIPT)
assert SPEC and SPEC.loader
collaborate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collaborate)


def main() -> None:
    registry = {"schema_version": 1, "topics": []}
    session = {
        "key": "topic-mimo-child", "topic": "topic", "provider": "mimo", "model_profile": "mimo",
        "working_directory": "/project", "workspace_identity": "workspace", "host_platform": "posix",
        "session_id": "uuid", "status": "active", "created_at": "now",
    }
    collaborate.register_topic_session(registry, session, "topic-mimo-parent")
    reference = registry["topics"][0]["sessions"][0]
    assert reference["parent_key"] == "topic-mimo-parent"
    assert reference["session_id"] == "uuid"
    assert reference["host_platform"] == "posix"
    assert registry["topics"][0]["status"] == "active"
    print("session-lifecycle tests passed")


if __name__ == "__main__":
    main()
