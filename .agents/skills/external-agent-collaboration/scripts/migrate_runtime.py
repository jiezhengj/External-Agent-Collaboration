#!/usr/bin/env python3
"""Report or quarantine session records that cannot safely cross host platforms."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platform_support import host_platform, record_host_platform


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONTROL_ROOT = PROJECT_ROOT / ".ai-collaboration"
SESSIONS_FILE = CONTROL_ROOT / "sessions.json"


def read_sessions() -> dict[str, Any]:
    if not SESSIONS_FILE.exists():
        return {"schema_version": 2, "sessions": []}
    data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
        raise ValueError("sessions.json must contain a sessions array.")
    return data


def incompatible_sessions(data: dict[str, Any]) -> list[dict[str, str]]:
    current = host_platform()
    results: list[dict[str, str]] = []
    for item in data.get("sessions", []):
        if not isinstance(item, dict) or item.get("status") != "active":
            continue
        recorded = record_host_platform(item)
        if recorded != current:
            results.append({"key": str(item.get("key", "(missing)")), "recorded_platform": recorded or "unknown"})
    return results


def backup_sessions() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = CONTROL_ROOT / "backups" / f"sessions-{stamp}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SESSIONS_FILE, destination)
    return destination


def apply_quarantine(data: dict[str, Any]) -> int:
    current = host_platform()
    changed = 0
    for item in data["sessions"]:
        if not isinstance(item, dict) or item.get("status") != "active":
            continue
        if record_host_platform(item) != current:
            item["status"] = "incompatible_platform"
            item["incompatible_reason"] = f"record belongs to {record_host_platform(item) or 'unknown'} host platform"
            changed += 1
    if changed:
        data["schema_version"] = max(2, int(data.get("schema_version", 1)))
        temporary = SESSIONS_FILE.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(SESSIONS_FILE)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Back up and quarantine foreign active sessions.")
    args = parser.parse_args()
    try:
        data = read_sessions()
        incompatible = incompatible_sessions(data)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    payload: dict[str, Any] = {
        "ok": True,
        "host_platform": host_platform(),
        "incompatible_sessions": incompatible,
        "applied": False,
    }
    if args.apply and incompatible:
        payload["backup_path"] = str(backup_sessions().relative_to(PROJECT_ROOT))
        payload["quarantined"] = apply_quarantine(data)
        payload["applied"] = True
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
