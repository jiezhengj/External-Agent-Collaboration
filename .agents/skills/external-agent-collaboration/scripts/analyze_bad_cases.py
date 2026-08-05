#!/usr/bin/env python3
"""Aggregate the Codex-only failure ledger without exposing its raw payloads."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def analyze(root: Path, since: str | None = None) -> dict:
    records = []
    for path in sorted(root.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        if since and str(record.get("occurred_at", "")) < since:
            continue
        records.append(record)
    def count(key: str) -> dict[str, int]:
        return dict(sorted(Counter(str(item.get(key, "unknown")) for item in records).items()))
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "total": len(records), "by_error_code": count("error_code"), "by_stage": count("stage"), "by_platform": count("host_platform"), "by_harness": count("selected_harness"), "by_provider": count("selected_provider"), "by_skill_revision": count("skill_revision")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default=".ai-collaboration/bad-cases")
    parser.add_argument("--since")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = analyze(Path(args.ledger), args.since)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
