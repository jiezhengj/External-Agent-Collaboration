#!/usr/bin/env python3
"""Migration command contract test without touching the Skill runtime."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("migrate_workspace_state.py")


def main() -> None:
    completed = subprocess.run([sys.executable, str(SCRIPT), "--dry-run"], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True and payload["mode"] == "dry-run"
    assert "sessions" in payload["records"] and "goals" in payload["records"]
    assert all("/Users/" not in json.dumps(value) for value in payload["records"].values())
    with tempfile.TemporaryDirectory(prefix="migration-contract-") as directory:
        assert Path(directory).is_dir()
    print("workspace migration tests passed")


if __name__ == "__main__":
    main()
