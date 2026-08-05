#!/usr/bin/env python3
"""Install the Skill globally as a verifiable link, never as a copy."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from workspace_context import skill_project_root


def source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_target() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return codex_home / "skills" / "external-agent-collaboration"


def same_source(target: Path, source: Path) -> bool:
    try:
        return target.exists() and os.path.samefile(target, source)
    except OSError:
        return False


def check(source: Path, target: Path) -> dict[str, object]:
    source = source.resolve()
    result: dict[str, object] = {"source": str(source), "target": str(target), "source_is_skill": source.name == "external-agent-collaboration", "skill_project_root": None, "samefile": same_source(target, source), "target_exists": target.exists(), "metadata_readable": (source / "SKILL.md").is_file(), "ledger_writable": False}
    try:
        result["skill_project_root"] = str(skill_project_root())
    except Exception:
        result["skill_project_root"] = None
    ledger = source.parent.parent.parent / ".ai-collaboration" / "bad-cases"
    try:
        ledger.mkdir(parents=True, exist_ok=True)
        result["ledger_writable"] = os.access(ledger, os.W_OK)
    except OSError:
        result["ledger_writable"] = False
    result["ok"] = bool(result["source_is_skill"] and result["metadata_readable"] and result["ledger_writable"] and (not target.exists() or result["samefile"]))
    return result


def apply(source: Path, target: Path) -> None:
    source = source.resolve()
    if target.exists() or target.is_symlink():
        if same_source(target, source):
            return
        raise RuntimeError("global Skill target already exists and resolves to another source")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(source, target, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        # Windows directory symlink may require Developer Mode/admin; junction
        # is the documented, narrow fallback for this installer only.
        completed = subprocess.run(["cmd", "/d", "/s", "/c", "mklink", "/J", str(target), str(source)], capture_output=True, text=True, shell=False, check=False)
        if completed.returncode != 0:
            raise RuntimeError("unable to create Skill symlink or junction")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--source", type=Path, default=source_root())
    parser.add_argument("--target", type=Path, default=default_target())
    args = parser.parse_args()
    try:
        if args.apply:
            apply(args.source, args.target)
        result = check(args.source, args.target)
        if args.dry_run:
            result["would_apply"] = not bool(result["target_exists"])
        print(__import__("json").dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 2
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
