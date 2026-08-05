#!/usr/bin/env python3
"""Crash/interrupt state remains resumable and bounded."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("construction_protocol.py")


def run(root: Path, *args: str) -> dict:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="construction-interrupted-") as directory:
        root = Path(directory)
        (root / "src").mkdir()
        common = ["--project-root", str(root), "--goal-id", "goal-1", "--actor", "codex"]
        run(root, "init-goal", *common)
        run(root, "start-run", *common, "--wp", "WP-0", "--requirement", "baseline", "--allow-path", "src", "--stop-condition", "resume")
        interrupted = run(root, "interrupt-run", *common, "--next-action", "re-read current checkpoint")
        assert interrupted["status"] == "in_progress_interrupted"
        resumed = run(root, "resume-summary", *common)
        assert resumed["status"] == "in_progress_interrupted" and Path(root / resumed["resume_path"]).is_file()
    print("construction interrupted/resume tests passed")


if __name__ == "__main__":
    main()
