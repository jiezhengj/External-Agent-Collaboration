#!/usr/bin/env python3
"""Attach Codex quality/adoption assessment to an existing anonymous metric event."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
METRICS = ROOT / ".ai-collaboration" / "provider-metrics.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--quality-score", type=float)
    parser.add_argument("--user-adopted", choices=("true", "false"))
    parser.add_argument("--rework-count", type=int)
    args = parser.parse_args()
    if args.quality_score is not None and not 0 <= args.quality_score <= 5:
        raise SystemExit("quality score must be in [0, 5].")
    if args.rework_count is not None and args.rework_count < 0:
        raise SystemExit("rework count must be non-negative.")
    data = json.loads(METRICS.read_text(encoding="utf-8"))
    matches = [event for event in data.get("events", []) if event.get("run_id") == args.run_id]
    if len(matches) != 1:
        raise SystemExit("No unique metric event for run ID.")
    event = matches[0]
    if args.quality_score is not None:
        event["quality_score"] = args.quality_score
    if args.user_adopted is not None:
        event["user_adopted"] = args.user_adopted == "true"
    if args.rework_count is not None:
        event["rework_count"] = args.rework_count
    METRICS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": args.run_id, "updated": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
