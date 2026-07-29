#!/usr/bin/env python3
"""Initialize local-only collaboration files without reading credentials."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CONTROL = ROOT / ".ai-collaboration"
EXAMPLE = CONTROL / "providers.local.example.json"
LOCAL = CONTROL / "providers.local.json"
RUNTIME_DIRS = ("handoffs", "outputs", "logs", "snapshots", "archives", "reviews")


def initialize() -> int:
    if not EXAMPLE.is_file():
        print(f"Missing public example: {EXAMPLE.relative_to(ROOT)}", file=sys.stderr)
        return 2
    CONTROL.mkdir(exist_ok=True)
    for name in RUNTIME_DIRS:
        (CONTROL / name).mkdir(exist_ok=True)
    if LOCAL.exists():
        print(f"Kept existing local profile: {LOCAL.relative_to(ROOT)}")
    else:
        shutil.copyfile(EXAMPLE, LOCAL)
        LOCAL.chmod(0o600)
        print(f"Created local profile from example: {LOCAL.relative_to(ROOT)}")
    print("Next: edit local profile values, create each configured CLAUDE_CONFIG_DIR, then run doctor.py.")
    print("This script never reads, prints, or sends credential values.")
    return 0


def check() -> int:
    missing = [name for name in RUNTIME_DIRS if not (CONTROL / name).is_dir()]
    print(f"public example: {'ok' if EXAMPLE.is_file() else 'missing'}")
    print(f"local profile: {'present' if LOCAL.is_file() else 'missing'}")
    print(f"runtime directories: {'ok' if not missing else 'missing ' + ', '.join(missing)}")
    print("Credentials are intentionally not read or checked by bootstrap.")
    return 0 if EXAMPLE.is_file() and LOCAL.is_file() and not missing else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init", action="store_true", help="Create local runtime directories and copy the public profile example once.")
    mode.add_argument("--check", action="store_true", help="Check local setup without reading credentials.")
    args = parser.parse_args()
    return initialize() if args.init else check()


if __name__ == "__main__":
    raise SystemExit(main())
