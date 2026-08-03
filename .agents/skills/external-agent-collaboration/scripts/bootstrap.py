#!/usr/bin/env python3
"""Initialize local-only collaboration files without reading credentials."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from platform_support import host_platform

ROOT = Path(__file__).resolve().parents[4]
CONTROL = ROOT / ".ai-collaboration"
EXAMPLE = CONTROL / "providers.local.example.json"
LOCAL = CONTROL / "providers.local.json"
SHARED_EXAMPLE = CONTROL / "providers.shared.example.json"
SHARED = CONTROL / "providers.shared.json"
PLATFORM_EXAMPLE = CONTROL / f"providers.local.{host_platform()}.example.json"
TRUST_EXAMPLE = CONTROL / "trusted-providers.local.example.json"
TRUST_LOCAL = CONTROL / "trusted-providers.local.json"
HARNESS_EXAMPLE = CONTROL / "harness-profiles.local.example.json"
HARNESS_LOCAL = CONTROL / "harness-profiles.local.json"
HARNESS_TRUST_EXAMPLE = CONTROL / "trusted-harnesses.local.example.json"
HARNESS_TRUST_LOCAL = CONTROL / "trusted-harnesses.local.json"
RUNTIME_DIRS = ("handoffs", "outputs", "logs", "snapshots", "archives", "reviews")
DURABLE_DIRS = ("topics", "goals")
DURABLE_TEMPLATES = {
    "project-context.md": "# Project context\n\nKeep only stable collaboration background here. Link to project artifacts instead of copying their content.\n",
    "decisions.md": "# Confirmed collaboration decisions\n\nRecord only decisions that cannot be recovered from project artifacts, with evidence links. Do not store prompts, transcripts, or credentials.\n",
}


def protect_local_file(path: Path) -> str | None:
    if host_platform() == "windows":
        return "Windows could not verify or tighten ACLs automatically; keep this ignored file in a user-only directory."
    try:
        path.chmod(0o600)
    except OSError as exc:
        return f"Could not restrict local file permissions: {exc}"
    return None


def initialize() -> int:
    if not EXAMPLE.is_file() or not SHARED_EXAMPLE.is_file() or not PLATFORM_EXAMPLE.is_file() or not TRUST_EXAMPLE.is_file() or not HARNESS_EXAMPLE.is_file() or not HARNESS_TRUST_EXAMPLE.is_file():
        print("Missing one or more public local-configuration examples.", file=sys.stderr)
        return 2
    CONTROL.mkdir(exist_ok=True)
    for name in RUNTIME_DIRS + DURABLE_DIRS:
        (CONTROL / name).mkdir(exist_ok=True)
    for name, content in DURABLE_TEMPLATES.items():
        path = CONTROL / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    if SHARED.exists():
        print(f"Kept shared portable profile: {SHARED.relative_to(ROOT)}")
    else:
        shutil.copyfile(SHARED_EXAMPLE, SHARED)
        print(f"Created shared portable profile from example: {SHARED.relative_to(ROOT)}")
    if LOCAL.exists():
        print(f"Kept existing local profile: {LOCAL.relative_to(ROOT)}")
    else:
        shutil.copyfile(EXAMPLE, LOCAL)
        warning = protect_local_file(LOCAL)
        if warning:
            print(f"Warning: {warning}", file=sys.stderr)
        print(f"Created local profile from example: {LOCAL.relative_to(ROOT)}")
    if TRUST_LOCAL.exists():
        print(f"Kept existing provider trust record: {TRUST_LOCAL.relative_to(ROOT)}")
    else:
        shutil.copyfile(TRUST_EXAMPLE, TRUST_LOCAL)
        warning = protect_local_file(TRUST_LOCAL)
        if warning:
            print(f"Warning: {warning}", file=sys.stderr)
        print(f"Created empty provider trust record: {TRUST_LOCAL.relative_to(ROOT)}")
    if HARNESS_LOCAL.exists():
        print(f"Kept existing harness profile: {HARNESS_LOCAL.relative_to(ROOT)}")
    else:
        shutil.copyfile(HARNESS_EXAMPLE, HARNESS_LOCAL)
        warning = protect_local_file(HARNESS_LOCAL)
        if warning:
            print(f"Warning: {warning}", file=sys.stderr)
        print(f"Created local harness profile: {HARNESS_LOCAL.relative_to(ROOT)}")
    if HARNESS_TRUST_LOCAL.exists():
        print(f"Kept existing harness trust record: {HARNESS_TRUST_LOCAL.relative_to(ROOT)}")
    else:
        shutil.copyfile(HARNESS_TRUST_EXAMPLE, HARNESS_TRUST_LOCAL)
        warning = protect_local_file(HARNESS_TRUST_LOCAL)
        if warning:
            print(f"Warning: {warning}", file=sys.stderr)
        print(f"Created empty harness trust record: {HARNESS_TRUST_LOCAL.relative_to(ROOT)}")
    print("Created missing minimal collaboration state without copying transcripts or provider output.")
    print(f"Next: copy/edit {PLATFORM_EXAMPLE.relative_to(ROOT)} as this host's Git-ignored provider profile, place direct auth_token values there, create each CLAUDE_CONFIG_DIR, and run doctor.py. During an authorized implementation, Codex records each current non-secret provider fingerprint with trust_provider.py before the first call. For Antigravity P2, configure only non-secret settings in {HARNESS_LOCAL.relative_to(ROOT)}, complete its one-time interactive login, then Codex records that profile fingerprint with trust_harness.py before its first consult.")
    print("This script never reads, prints, or sends credential values.")
    return 0


def check() -> int:
    missing = [name for name in RUNTIME_DIRS + DURABLE_DIRS if not (CONTROL / name).is_dir()]
    missing_templates = [name for name in DURABLE_TEMPLATES if not (CONTROL / name).is_file()]
    print(f"public examples: {'ok' if EXAMPLE.is_file() and SHARED_EXAMPLE.is_file() and PLATFORM_EXAMPLE.is_file() and TRUST_EXAMPLE.is_file() and HARNESS_EXAMPLE.is_file() and HARNESS_TRUST_EXAMPLE.is_file() else 'missing'}")
    print(f"shared portable profile: {'present' if SHARED.is_file() else 'missing'}")
    print(f"local profile: {'present' if LOCAL.is_file() else 'missing'}")
    print(f"provider trust record: {'present' if TRUST_LOCAL.is_file() else 'missing'}")
    print(f"harness profile/trust: {'present' if HARNESS_LOCAL.is_file() and HARNESS_TRUST_LOCAL.is_file() else 'missing'}")
    print(f"runtime directories: {'ok' if not missing else 'missing ' + ', '.join(missing)}")
    print(f"minimal durable state: {'ok' if not missing_templates else 'missing ' + ', '.join(missing_templates)}")
    print("Credentials are intentionally not read or checked by bootstrap.")
    return 0 if EXAMPLE.is_file() and SHARED_EXAMPLE.is_file() and PLATFORM_EXAMPLE.is_file() and SHARED.is_file() and TRUST_EXAMPLE.is_file() and HARNESS_EXAMPLE.is_file() and HARNESS_TRUST_EXAMPLE.is_file() and LOCAL.is_file() and TRUST_LOCAL.is_file() and HARNESS_LOCAL.is_file() and HARNESS_TRUST_LOCAL.is_file() and not missing and not missing_templates else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--init", action="store_true", help="Create local runtime directories and copy the public profile example once.")
    mode.add_argument("--check", action="store_true", help="Check local setup without reading credentials.")
    args = parser.parse_args()
    return initialize() if args.init else check()


if __name__ == "__main__":
    raise SystemExit(main())
