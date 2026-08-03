#!/usr/bin/env python3
"""Run the dependency-free cross-platform regression suite."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
PYTHON_CACHE = PROJECT_ROOT / ".ai-collaboration" / "pycache"


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def main() -> int:
    tests = sorted(SCRIPT_DIR.glob("test_*.py"))
    if not tests:
        raise SystemExit("No regression tests were found.")
    for test in tests:
        run([sys.executable, str(test)])

    environment = os.environ.copy()
    environment["PYTHONPYCACHEPREFIX"] = str(PYTHON_CACHE)
    run([sys.executable, "-m", "compileall", "-q", str(SCRIPT_DIR)], env=environment)
    run([
        sys.executable,
        str(SCRIPT_DIR / "goal_lifecycle.py"),
        "--project-root",
        ".",
        "validate",
        "--contract",
        ".agents/skills/external-agent-collaboration/references/goal-contract.example.json",
    ])
    print(f"cross-platform regression passed: {len(tests)} test scripts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
