#!/usr/bin/env python3
"""Regression tests for Claude-first harness identity and dry-run migration."""

from __future__ import annotations

import copy
import importlib.util
import os
import json
import sys
import tempfile
from pathlib import Path


def load(name: str):
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


state = load("harness_state.py")
migrate = load("migrate_harness_state.py")
collaborate = load("collaborate.py")


def main() -> None:
    session_data = {"schema_version": 1, "sessions": [{
        "key": "legacy", "provider": "deepseek", "model_profile": "deepseek", "session_id": "claude-id",
        "host_platform": "macos", "status": "active",
    }]}
    migrated, count = migrate.annotate("sessions", copy.deepcopy(session_data))
    record = migrated["sessions"][0]
    assert count == 1 and migrated["schema_version"] == state.RUNTIME_SCHEMA_VERSION
    assert record["harness"] == state.CLAUDE_CODE and record["harness_profile"] == "deepseek"
    assert record["external_session_id"] == record["session_id"] == "claude-id"

    for name, data in {
        "trust": {"schema_version": 1, "providers": {"deepseek": {"approved": True}}},
        "health": {"schema_version": 1, "providers": {"deepseek": {"state": "healthy"}}},
        "capabilities": {"schema_version": 1, "providers": {"deepseek": {"native_write": True}}},
        "metrics": {"schema_version": 1, "events": [{"provider": "deepseek", "model_profile": "deepseek"}]},
    }.items():
        migrated, count = migrate.annotate(name, copy.deepcopy(data))
        assert count == 1 and migrated["schema_version"] == state.RUNTIME_SCHEMA_VERSION
        target = migrated["events"][0] if name == "metrics" else migrated["providers"]["deepseek"]
        assert target["harness"] == state.CLAUDE_CODE and target["harness_profile"] == "deepseek"

    foreign = {"harness": "antigravity", "external_session_id": "agy-id"}
    changed = state.decorate_legacy_record(foreign, "agy")
    assert not changed and foreign == {"harness": "antigravity", "external_session_id": "agy-id"}
    assert state.external_session_id(record) == "claude-id"

    workdir = Path.cwd()
    original_flag = os.environ.get("EXTERNAL_AGENT_HARNESS_STATE")
    os.environ["EXTERNAL_AGENT_HARNESS_STATE"] = "1"
    try:
        try:
            collaborate.select_provider(
                "auto", "topic", workdir,
                [{"status": "active", "topic": "topic", "working_directory": str(workdir),
                  "workspace_identity": collaborate.workspace_identity(workdir), "host_platform": collaborate.host_platform(),
                  "provider": "agy", "harness": "antigravity", "key": "foreign"}],
                {"deepseek": {}}, {"round_robin_cursor": {}, "events": []}, {"schema_version": 1, "providers": {}}, "planning", "analyze",
            )
        except collaborate.CollaborationError as exc:
            assert "different harness" in str(exc)
        else:
            raise AssertionError("foreign harness session must not be continued by Claude Code when the feature is enabled")
    finally:
        if original_flag is None:
            os.environ.pop("EXTERNAL_AGENT_HARNESS_STATE", None)
        else:
            os.environ["EXTERNAL_AGENT_HARNESS_STATE"] = original_flag

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        control = root / ".ai-collaboration"
        control.mkdir()
        sessions = control / "sessions.json"
        sessions.write_text(json.dumps(session_data), encoding="utf-8")
        original_root, original_control, original_files, original_argv = migrate.PROJECT_ROOT, migrate.CONTROL_ROOT, migrate.RUNTIME_FILES, sys.argv
        migrate.PROJECT_ROOT, migrate.CONTROL_ROOT = root, control
        migrate.RUNTIME_FILES = {"sessions": sessions}
        sys.argv = ["migrate_harness_state.py", "--apply"]
        try:
            assert migrate.main() == 0
            updated = json.loads(sessions.read_text(encoding="utf-8"))
            assert updated["sessions"][0]["harness"] == state.CLAUDE_CODE
            assert list((control / "backups").glob("sessions-*.json"))
        finally:
            migrate.PROJECT_ROOT, migrate.CONTROL_ROOT, migrate.RUNTIME_FILES, sys.argv = original_root, original_control, original_files, original_argv
    print("harness-state tests passed")


if __name__ == "__main__":
    main()
