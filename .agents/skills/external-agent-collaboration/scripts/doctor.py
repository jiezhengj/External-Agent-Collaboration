#!/usr/bin/env python3
"""Check external-collaboration prerequisites without reading secret values."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from platform_support import macos_keychain_supported, macos_keychain_unavailable_message
from profile_support import ProfileConfigError, environment_token, load_profiles as load_profile_documents, profile_file_paths


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONTROL_ROOT = PROJECT_ROOT / ".ai-collaboration"
def load_profiles() -> dict:
    try:
        return load_profiles_from_control()
    except ProfileConfigError as exc:
        raise ValueError(str(exc)) from exc


def load_profiles_from_control() -> dict:
    return load_profile_documents(CONTROL_ROOT)


def check(provider: str) -> list[str]:
    profiles = load_profiles()
    profile = profiles.get(provider)
    if not isinstance(profile, dict):
        shared, local = profile_file_paths(CONTROL_ROOT)
        return [f"Provider '{provider}' is not configured in {shared.name} or {local.name}."]

    problems: list[str] = []
    launcher = str(profile.get("launcher", "claude"))
    if not (Path(launcher).is_file() or shutil.which(launcher)):
        problems.append(f"Claude launcher is unavailable: {launcher}")

    config_dir = profile.get("config_dir")
    if not isinstance(config_dir, str) or not Path(config_dir).is_dir():
        problems.append("Configured CLAUDE_CONFIG_DIR does not exist or is not a directory.")

    direct_token = profile.get("auth_token")
    service = profile.get("auth_token_keychain_service")
    if isinstance(direct_token, str) and direct_token:
        pass
    elif isinstance(profile.get("auth_token_env"), str) and profile.get("auth_token_env"):
        if not environment_token(profile):
            problems.append(f"Missing authentication environment variable: {profile['auth_token_env']}")
    elif isinstance(service, str) and service:
        if not macos_keychain_supported():
            problems.append(macos_keychain_unavailable_message())
        else:
            try:
                result = subprocess.run(["security", "find-generic-password", "-s", service], capture_output=True, text=True)
            except OSError:
                problems.append("macOS Keychain command is unavailable.")
            else:
                if result.returncode != 0:
                    problems.append(f"Missing macOS Keychain password item: {service}")
    else:
        required = profile.get("required_environment", [])
        if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
            problems.append("Provide auth_token, auth_token_keychain_service, or required_environment.")
        else:
            missing = [name for name in required if not os.environ.get(name)]
            if missing:
                problems.append("Missing required environment variables: " + ", ".join(missing))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, help="Provider key from providers.shared.json or providers.local.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        problems = check(args.provider)
    except ValueError as exc:
        problems = [str(exc)]
    payload = {"provider": args.provider, "ok": not problems, "problems": problems}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    elif problems:
        print("External-agent profile is not ready:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
    else:
        print(f"{args.provider} profile is ready.")
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())
