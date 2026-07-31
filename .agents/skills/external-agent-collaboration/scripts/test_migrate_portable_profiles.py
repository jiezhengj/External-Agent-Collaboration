#!/usr/bin/env python3
"""Regression tests for non-printing portable-profile configuration migration."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("migrate_portable_profiles.py")
SPEC = importlib.util.spec_from_file_location("migrate_portable_profiles", SCRIPT)
assert SPEC and SPEC.loader
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        control = Path(directory)
        (control / "providers.local.json").write_text(json.dumps({
            "mimo": {
                "config_dir": "/Users/example/.claude-mimo",
                "launcher": "/Users/example/.local/bin/claude",
                "auth_token": "test-token-value",
                "environment": {"ANTHROPIC_BASE_URL": "https://provider.example/anthropic", "API_KEY": "must-not-copy"},
            }
        }), encoding="utf-8")
        (control / "providers.shared.json").write_text('{"schema_version": 1, "providers": {}}\n', encoding="utf-8")
        original_control, original_state, original_platform = migration.CONTROL_ROOT, migration.MIGRATION_STATE, migration.host_platform
        migration.CONTROL_ROOT = control
        migration.MIGRATION_STATE = control / "providers.migration.json"
        migration.host_platform = lambda: "windows"
        try:
            result = migration.apply(migration.legacy_profiles(), home=control / "home")
        finally:
            migration.CONTROL_ROOT, migration.MIGRATION_STATE, migration.host_platform = original_control, original_state, original_platform
        assert result["migrated_providers"] == ["mimo"]
        assert result["initialized_config_directories"] == ["mimo"]
        shared_text = (control / "providers.shared.json").read_text(encoding="utf-8")
        assert "test-token-value" not in shared_text and "API_KEY" not in shared_text
        shared = json.loads(shared_text)["providers"]["mimo"]
        assert shared["config_dir_relative_to_home"] == ".claude-mimo"
        assert shared["launcher"] == "claude"
        assert (control / "home" / ".claude-mimo").is_dir()
        overlay = json.loads((control / "providers.local.windows.json").read_text(encoding="utf-8"))["providers"]["mimo"]
        assert overlay == {"auth_token": "test-token-value"}
        (control / "providers.local.macos.json").write_text('{"schema_version": 1, "providers": {"mimo": {"auth_token": "test-token-value"}}}\n', encoding="utf-8")
        migration.CONTROL_ROOT, migration.MIGRATION_STATE = control, control / "providers.migration.json"
        try:
            cleanup = migration.cleanup_legacy(home=control / "backup-home")
        finally:
            migration.CONTROL_ROOT, migration.MIGRATION_STATE = original_control, original_state
        assert cleanup["legacy_profile_cleaned"] is True
        assert "test-token-value" not in (control / "providers.local.json").read_text(encoding="utf-8")
        assert (control / "backup-home" / ".external-agent-collaboration" / "providers.local.legacy-backup.json").is_file()

    with tempfile.TemporaryDirectory() as directory:
        control = Path(directory)
        (control / "providers.local.json").write_text(json.dumps({
            "mimo": {"config_dir": "/Users/example/.claude-mimo", "launcher": "/Users/example/.local/bin/claude", "auth_token": "test-token-value"}
        }), encoding="utf-8")
        (control / "providers.shared.json").write_text('{"schema_version": 1, "providers": {}}\n', encoding="utf-8")
        original_control, original_state, original_platform = migration.CONTROL_ROOT, migration.MIGRATION_STATE, migration.host_platform
        migration.CONTROL_ROOT, migration.MIGRATION_STATE, migration.host_platform = control, control / "providers.migration.json", lambda: "macos"
        try:
            migration.apply(migration.legacy_profiles(), home=control / "home")
        finally:
            migration.CONTROL_ROOT, migration.MIGRATION_STATE, migration.host_platform = original_control, original_state, original_platform
        overlay = json.loads((control / "providers.local.macos.json").read_text(encoding="utf-8"))["providers"]["mimo"]
        assert overlay["config_dir"] == "/Users/example/.claude-mimo"
        assert overlay["launcher"] == "/Users/example/.local/bin/claude"
    print("portable-profile migration tests passed")


if __name__ == "__main__":
    main()
