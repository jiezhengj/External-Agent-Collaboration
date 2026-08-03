#!/usr/bin/env python3
"""Regression tests for bounded cross-platform CLI process cleanup."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

from process_support import run_bounded


def main() -> None:
    quick = run_bounded(
        [sys.executable, "-c", "print('ok')"],
        cwd=Path.cwd(), env=os.environ.copy(), timeout=5,
    )
    assert quick.returncode == 0 and quick.stdout.strip() == "ok" and not quick.timed_out

    started = time.monotonic()
    slow = run_bounded(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=Path.cwd(), env=os.environ.copy(), timeout=0.2,
    )
    elapsed = time.monotonic() - started
    assert slow.returncode == 124 and slow.timed_out and elapsed < 5

    started = time.monotonic()
    descendant = run_bounded(
        [
            sys.executable,
            "-c",
            "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)",
        ],
        cwd=Path.cwd(), env=os.environ.copy(), timeout=0.2,
    )
    elapsed = time.monotonic() - started
    assert descendant.returncode == 124 and descendant.timed_out and elapsed < 5
    print("process-support tests passed")


if __name__ == "__main__":
    main()
