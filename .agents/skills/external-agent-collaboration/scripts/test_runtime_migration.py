#!/usr/bin/env python3
"""Regression tests for conservative foreign-session quarantine."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import platform_support


SCRIPT = Path(__file__).with_name("migrate_runtime.py")
SPEC = importlib.util.spec_from_file_location("migrate_runtime", SCRIPT)
assert SPEC and SPEC.loader
migrate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migrate)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        sessions_file = Path(directory) / "sessions.json"
        foreign_platform = "windows" if platform_support.host_platform() != "windows" else "macos"
        foreign_workdir = "C:/Users/example/project" if foreign_platform == "windows" else "/Users/example/project"
        sessions_file.write_text(json.dumps({"schema_version": 1, "sessions": [{"key": "foreign", "status": "active", "working_directory": foreign_workdir, "host_platform": foreign_platform}]}), encoding="utf-8")
        original = migrate.SESSIONS_FILE
        migrate.SESSIONS_FILE = sessions_file
        try:
            data = migrate.read_sessions()
            assert migrate.incompatible_sessions(data)
            assert migrate.apply_quarantine(data) == 1
            updated = migrate.read_sessions()
            assert updated["schema_version"] == 2
            assert updated["sessions"][0]["status"] == "incompatible_platform"
        finally:
            migrate.SESSIONS_FILE = original
    print("runtime-migration tests passed")


if __name__ == "__main__":
    main()
