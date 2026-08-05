#!/usr/bin/env python3
"""Check Antigravity local prerequisites without attempting authentication or a model request."""

from __future__ import annotations

import argparse
import json
import shutil

import collaborate
from antigravity_adapter import AntigravityAdapter
from harness_profile_support import HarnessProfileError, load_profiles, trusted


def harness_control():
    # Preserve the module-level test/embedding override while real invocations
    # use the Skill-shared profile and trust registry.
    return collaborate.CONTROL_ROOT if collaborate.CONTROL_ROOT != collaborate.CONTEXT.target_control_root else collaborate.SHARED_CONTROL_ROOT


def check(profile_name: str) -> dict[str, object]:
    control = harness_control()
    profiles = load_profiles(control)
    profile = profiles.get(profile_name)
    if not profile:
        raise HarnessProfileError(f"Harness profile '{profile_name}' is not configured.")
    problems = AntigravityAdapter.doctor(profile)
    launcher = str(profile.get("launcher", "agy"))
    if not shutil.which(launcher):
        problems.append(f"Antigravity launcher is unavailable: {launcher}")
    return {
        "harness": "antigravity", "profile": profile_name, "ok": not problems and trusted(control, profile_name, profile),
        "profile_trusted": trusted(control, profile_name, profile), "interactive_authentication": "not_checked_without_a_real_request",
        "problems": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="antigravity_readonly")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        payload = check(args.profile)
    except HarnessProfileError as exc:
        payload = {"harness": "antigravity", "profile": args.profile, "ok": False, "problems": [str(exc)]}
    print(json.dumps(payload, ensure_ascii=False) if args.json else payload)
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
