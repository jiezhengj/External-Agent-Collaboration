#!/usr/bin/env python3
"""Request one bounded, independent critique of a completed external execution."""

from __future__ import annotations

import argparse
import json
import subprocess
import hashlib
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from workspace_context import skill_project_root
from failure_events import write_failure_event


ROOT = skill_project_root()
CONTROL = ROOT / ".ai-collaboration"
COLLABORATE = Path(__file__).with_name("collaborate.py")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    return data


def review_provider(source: str, requested: str) -> str:
    if requested == "auto":
        raise ValueError("Specify --provider for an independent critique; provider profiles are user-defined.")
    if requested == source:
        raise ValueError("Independent critique must use a provider other than the executor.")
    return requested


def handoff_text(record: dict[str, Any]) -> str:
    changed = record.get("changed_files", [])
    outcomes = record.get("outcome_results", [])
    return "\n".join([
        "# Independent execution critique",
        "",
        f"Review the completed external execution for topic: {record.get('topic')}",
        "Do not edit files or invoke another agent. Inspect only the listed changed files and relevant local tests.",
        f"Changed files: {', '.join(changed) if changed else '(none)'}",
        f"Machine outcome summary: {json.dumps(outcomes, ensure_ascii=False)}",
        "Return: material defects; missing tests; security/scope concerns; and a concise approve/needs-rework recommendation.",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--provider", required=True, help="Configured provider key other than the executor")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--invocation-id", default=f"review-{time.time_ns()}", help=argparse.SUPPRESS)
    args = parser.parse_args()
    source_path = CONTROL / "outputs" / f"{args.run_id}.json"
    try:
        record = load(source_path)
        if record.get("status") != "completed" or record.get("action") != "execute":
            raise ValueError("Only a completed execute result can receive an independent critique.")
        reviewer = review_provider(str(record.get("provider")), args.provider)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        write_failure_event(__import__("workspace_context").default_context(), invocation_id=args.invocation_id, error_code="validation_failed", stage="review_execution", message=str(exc))
        print(str(exc), file=sys.stderr)
        return 2
    handoff = CONTROL / "handoffs" / f"review-{args.run_id}.md"
    handoff.write_text(handoff_text(record), encoding="utf-8")
    command = [
        sys.executable, str(COLLABORATE), "--action", "critique", "--provider", reviewer,
        "--topic", f"independent review {args.run_id}", "--handoff", str(handoff.relative_to(ROOT)),
        "--task-type", str(record.get("task_type", "code")), "--mode", "critique", "--ephemeral",
        "--timeout", str(args.timeout), "--invocation-id", args.invocation_id,
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    review = {"run_id": args.run_id, "reviewer": reviewer, "reviewed_at": now(), "exit_code": result.returncode, "stdout_sha256": hashlib.sha256(result.stdout.encode("utf-8", "replace")).hexdigest(), "stderr_sha256": hashlib.sha256(result.stderr.encode("utf-8", "replace")).hexdigest(), "result_summary": " ".join((result.stdout or result.stderr).split())[:500]}
    target = CONTROL / "reviews" / f"{args.run_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"reviewer": reviewer, "review_file": str(target.relative_to(ROOT)), "exit_code": result.returncode}, ensure_ascii=False))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
