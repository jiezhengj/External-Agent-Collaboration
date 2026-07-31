#!/usr/bin/env python3
"""Record or revoke user approval for a non-secret local harness profile."""

from __future__ import annotations

import argparse
import json

from harness_profile_support import HarnessProfileError, load_profiles, profile_fingerprint, trust_path

from collaborate import CONTROL_ROOT, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--approve", action="store_true")
    group.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    profiles = load_profiles(CONTROL_ROOT)
    profile = profiles.get(args.profile)
    if not profile:
        raise HarnessProfileError(f"Harness profile '{args.profile}' is not configured.")
    path = trust_path(CONTROL_ROOT)
    data = {"schema_version": 1, "profiles": {}}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
        raise HarnessProfileError("trusted-harnesses.local.json must contain a profiles object.")
    if args.approve:
        data["profiles"][args.profile] = {"approved": True, "harness": "antigravity", "profile_fingerprint": profile_fingerprint(profile)}
        write_json(path, data)
        print(f"Approved local harness profile '{args.profile}'. No credential was read or printed.")
    else:
        data["profiles"].pop(args.profile, None)
        write_json(path, data)
        print(f"Revoked local harness profile '{args.profile}'.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessProfileError as exc:
        print(str(exc))
        raise SystemExit(2)
