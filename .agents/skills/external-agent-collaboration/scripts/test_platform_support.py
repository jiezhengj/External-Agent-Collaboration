#!/usr/bin/env python3
"""Regression tests for platform-safe workspace and capability matching."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import platform_support
import probe_capabilities


def main() -> None:
    assert platform_support.infer_path_platform("/Users/example/project") == "macos"
    assert platform_support.infer_path_platform("C:/Users/example/project") == "windows"
    assert platform_support.infer_path_platform("/srv/project") == "posix"
    with tempfile.TemporaryDirectory() as directory:
        workdir = Path(directory)
        session = {
            "host_platform": platform_support.host_platform(),
            "working_directory": str(workdir.resolve()),
            "workspace_identity": platform_support.workspace_identity(workdir),
        }
        assert platform_support.session_matches_workspace(session, workdir)
        foreign = {"working_directory": "/Users/example/project"}
        assert not platform_support.session_matches_workspace(foreign, workdir)
        assert platform_support.capability_matches_host({"host_platform": platform_support.host_platform()})
        assert not platform_support.capability_matches_host({"host_platform": "other"})
        record = {
            "host_platform": platform_support.host_platform(), "profile_fingerprint": "fingerprint",
            "claude_cli_version": "version", "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        assert probe_capabilities.fresh(record, "fingerprint", "version", 1)
        record["host_platform"] = "other"
        assert not probe_capabilities.fresh(record, "fingerprint", "version", 1)
    print("platform-support tests passed")


if __name__ == "__main__":
    main()
