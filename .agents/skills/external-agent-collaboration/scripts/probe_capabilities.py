#!/usr/bin/env python3
"""Empirically probe a provider's Claude Code file-tool capabilities."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONTROL_ROOT = PROJECT_ROOT / ".ai-collaboration"
PROFILE_FILE = CONTROL_ROOT / "providers.local.json"
CAPABILITIES_FILE = CONTROL_ROOT / "provider-capabilities.json"
COLLABORATE = Path(__file__).with_name("collaborate.py")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def profile_fingerprint(profile: dict[str, Any]) -> str:
    safe = {key: value for key, value in profile.items() if key not in {"auth_token", "auth_token_keychain_service"}}
    return hashlib.sha256(json.dumps(safe, sort_keys=True).encode()).hexdigest()


def cli_version(profile: dict[str, Any]) -> str:
    result = subprocess.run([str(profile.get("launcher", "claude")), "--version"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def fresh(record: dict[str, Any] | None, fingerprint: str, version: str, max_age_hours: int) -> bool:
    if not record or record.get("profile_fingerprint") != fingerprint or record.get("claude_cli_version") != version:
        return False
    try:
        checked = datetime.fromisoformat(str(record["checked_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    return checked >= datetime.now(timezone.utc) - timedelta(hours=max_age_hours)


def invoke(provider: str, topic: str, handoff: Path, outcomes: Path, target: Path, commands: list[str]) -> tuple[int, str]:
    command = [
        sys.executable, str(COLLABORATE), "--action", "execute", "--provider", provider,
        "--topic", topic, "--handoff", str(handoff.relative_to(PROJECT_ROOT)),
        "--allow-path", str(target.relative_to(PROJECT_ROOT)), "--expected-outcomes", str(outcomes.relative_to(PROJECT_ROOT)),
        "--ephemeral", "--timeout", "240", "--skip-capability-check",
    ]
    for item in commands:
        command.extend(["--allow-command", item])
    result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True)
    return result.returncode, result.stdout[-4000:] + result.stderr[-4000:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, help="Provider key from providers.local.json")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-age-hours", type=int, default=168)
    args = parser.parse_args()

    profiles = read_json(PROFILE_FILE, {})
    profile = profiles.get(args.provider)
    if not isinstance(profile, dict):
        print(f"Provider profile unavailable: {args.provider}", file=sys.stderr)
        return 2
    fingerprint = profile_fingerprint(profile)
    version = cli_version(profile)
    data = read_json(CAPABILITIES_FILE, {"schema_version": 1, "providers": {}})
    existing = data.setdefault("providers", {}).get(args.provider)
    if not args.force and fresh(existing, fingerprint, version, args.max_age_hours):
        print(json.dumps({"provider": args.provider, "probed": False, "record": existing}, ensure_ascii=False, indent=2))
        return 0

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lab = PROJECT_ROOT / "capability-lab" / args.provider / run_id
    lab.mkdir(parents=True, exist_ok=False)
    native_target = lab / "native-write.md"
    native_handoff = CONTROL_ROOT / "handoffs" / f"capability-{args.provider}-{run_id}-native.md"
    native_outcomes = CONTROL_ROOT / "handoffs" / f"capability-{args.provider}-{run_id}-native.outcomes.json"
    native_handoff.write_text(
        f"Create the new file `{native_target.relative_to(PROJECT_ROOT)}` with exactly the title `# native write probe`. "
        "Do not run Shell commands and do not modify any other file.", encoding="utf-8"
    )
    write_json(native_outcomes, {"outcomes": [{"type": "file_equals", "path": str(native_target.relative_to(PROJECT_ROOT)), "text": "# native write probe"}]})
    native_exit, native_output = invoke(args.provider, f"capability probe {args.provider}", native_handoff, native_outcomes, native_target, [])
    native_write = native_exit == 0 and native_target.read_text(encoding="utf-8").strip() == "# native write probe" if native_target.exists() else False

    bash_create = None
    fallback_exit = None
    fallback_output = ""
    if not native_write:
        fallback_target = lab / "bash-create.md"
        touch = f"touch {fallback_target.relative_to(PROJECT_ROOT)}"
        fallback_handoff = CONTROL_ROOT / "handoffs" / f"capability-{args.provider}-{run_id}-bash.md"
        fallback_outcomes = CONTROL_ROOT / "handoffs" / f"capability-{args.provider}-{run_id}-bash.outcomes.json"
        fallback_handoff.write_text(
            f"Use only the approved command `{touch}` to create `{fallback_target.relative_to(PROJECT_ROOT)}`, then use Edit to write exactly `# bash create probe`. "
            "Do not run other Shell commands and do not modify any other file.", encoding="utf-8"
        )
        write_json(fallback_outcomes, {"outcomes": [{"type": "file_equals", "path": str(fallback_target.relative_to(PROJECT_ROOT)), "text": "# bash create probe"}]})
        fallback_exit, fallback_output = invoke(args.provider, f"capability probe {args.provider}", fallback_handoff, fallback_outcomes, fallback_target, [touch])
        bash_create = fallback_exit == 0 and fallback_target.exists() and fallback_target.read_text(encoding="utf-8").strip() == "# bash create probe"

    record = {
        "checked_at": now(), "profile_fingerprint": fingerprint, "claude_cli_version": version,
        "native_write": native_write, "bash_create_fallback": bash_create,
        "evidence": {"native_exit_code": native_exit, "fallback_exit_code": fallback_exit},
        "lab_directory": str(lab.relative_to(PROJECT_ROOT)),
    }
    data["providers"][args.provider] = record
    write_json(CAPABILITIES_FILE, data)
    print(json.dumps({"provider": args.provider, "probed": True, "record": record}, ensure_ascii=False, indent=2))
    return 0 if native_write or bash_create else 3


if __name__ == "__main__":
    raise SystemExit(main())
