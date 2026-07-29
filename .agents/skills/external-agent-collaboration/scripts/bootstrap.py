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
DURABLE_DIRS = ("topics",)
DURABLE_TEMPLATES = {
    "project-context.md": "# Project context\n\nKeep only stable collaboration background here. Link to project artifacts instead of copying their content.\n",
    "decisions.md": "# Confirmed collaboration decisions\n\nRecord only decisions that cannot be recovered from project artifacts, with evidence links. Do not store prompts, transcripts, or credentials.\n",
}


def initialize() -> int:
    if not EXAMPLE.is_file():
        print(f"Missing public example: {EXAMPLE.relative_to(ROOT)}", file=sys.stderr)
        return 2
    CONTROL.mkdir(exist_ok=True)
    for name in RUNTIME_DIRS + DURABLE_DIRS:
        (CONTROL / name).mkdir(exist_ok=True)
    for name, content in DURABLE_TEMPLATES.items():
        path = CONTROL / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    if LOCAL.exists():
        print(f"Kept existing local profile: {LOCAL.relative_to(ROOT)}")
    else:
        shutil.copyfile(EXAMPLE, LOCAL)
        LOCAL.chmod(0o600)
        print(f"Created local profile from example: {LOCAL.relative_to(ROOT)}")
    print("Created missing minimal collaboration state without copying transcripts or provider output.")
    print("Next: edit local profile values, create each configured CLAUDE_CONFIG_DIR, then run doctor.py.")
    print("This script never reads, prints, or sends credential values.")
    return 0


def check() -> int:
    missing = [name for name in RUNTIME_DIRS + DURABLE_DIRS if not (CONTROL / name).is_dir()]
    missing_templates = [name for name in DURABLE_TEMPLATES if not (CONTROL / name).is_file()]
    print(f"public example: {'ok' if EXAMPLE.is_file() else 'missing'}")
    print(f"local profile: {'present' if LOCAL.is_file() else 'missing'}")
    print(f"runtime directories: {'ok' if not missing else 'missing ' + ', '.join(missing)}")
    print(f"minimal durable state: {'ok' if not missing_templates else 'missing ' + ', '.join(missing_templates)}")
    print("Credentials are intentionally not read or checked by bootstrap.")
    return 0 if EXAMPLE.is_file() and LOCAL.is_file() and not missing and not missing_templates else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init", action="store_true", help="Create local runtime directories and copy the public profile example once.")
    mode.add_argument("--check", action="store_true", help="Check local setup without reading credentials.")
    args = parser.parse_args()
    return initialize() if args.init else check()


if __name__ == "__main__":
    raise SystemExit(main())
