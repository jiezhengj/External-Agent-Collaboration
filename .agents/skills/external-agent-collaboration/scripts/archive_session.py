#!/usr/bin/env python3
"""Archive a known collaboration session and write a durable local index."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
CONTROL = ROOT / ".ai-collaboration"
SESSIONS = CONTROL / "sessions.json"
TOPICS = CONTROL / "topics.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, fallback: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-key", required=True)
    parser.add_argument("--summary-file")
    args = parser.parse_args()
    data = load(SESSIONS, {"schema_version": 1, "sessions": []})
    matches = [item for item in data["sessions"] if item.get("key") == args.session_key and item.get("status") == "active"]
    if len(matches) != 1:
        raise SystemExit("No unique active session with the requested key.")
    session = matches[0]
    summary = "No additional summary was supplied. Read shared project state and the recorded output index before continuing."
    if args.summary_file:
        path = Path(args.summary_file).resolve()
        try:
            path.relative_to(ROOT)
        except ValueError as exc:
            raise SystemExit("Summary file must be inside the project.") from exc
        summary = path.read_text(encoding="utf-8")
        lowered = summary.lower()
        if any(marker in lowered for marker in ("sk-", "api key", "password", "private key", ".env")):
            raise SystemExit("Summary appears to contain sensitive content; redact it before archiving.")
    session["status"] = "archived"
    session["archived_at"] = now()
    SESSIONS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    topics = load(TOPICS, {"schema_version": 1, "topics": []})
    for topic in topics["topics"]:
        for reference in topic.get("sessions", []):
            if reference.get("key") == args.session_key:
                reference["status"] = "archived"
        if topic.get("topic") == session["topic"] and topic.get("working_directory") == session["working_directory"]:
            topic["status"] = "archived" if all(item.get("status") == "archived" for item in topic.get("sessions", [])) else "active"
            topic["last_used_at"] = now()
    TOPICS.write_text(json.dumps(topics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    destination = CONTROL / "archives" / f"{args.session_key}.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(f"# Archived collaboration session\n\n- topic: {session['topic']}\n- provider: {session['provider']}\n- model profile: {session['model_profile']}\n- working directory: {session['working_directory']}\n- session key: {session['key']}\n- archived at: {session['archived_at']}\n\n## Handoff summary\n\n{summary}\n", encoding="utf-8")
    print(destination.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
