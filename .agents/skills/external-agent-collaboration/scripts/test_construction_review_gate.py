#!/usr/bin/env python3
"""Accepted review gates authorize exactly the next WP."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("construction_protocol.py")


def run(root: Path, *args: str) -> dict:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="construction-gate-") as directory:
        root = Path(directory)
        (root / "src").mkdir()
        common = ["--project-root", str(root), "--goal-id", "goal-1", "--actor", "codex"]
        run(root, "init-goal", *common)
        run(root, "start-run", *common, "--wp", "WP-0", "--requirement", "baseline", "--allow-path", "src", "--stop-condition", "review")
        report = {"report_type": "construction_stage_report", "schema_version": 1, "goal_id": "goal-1", "wp_id": "WP-0", "proposed_status": "ready_for_review", "implementation_summary": "baseline", "requirement_claims": [{"requirement_id": "baseline", "claimed_status": "passed", "claimed_evidence": []}], "decisions": [], "deviations": [], "commands_claimed": [], "unresolved_risks": [], "requested_review": [], "proposed_next_action": "review"}
        (root / "report.json").write_text(json.dumps(report), encoding="utf-8")
        checkpoint = run(root, "materialize-checkpoint", *common, "--wp", "WP-0", "--report", "report.json", "--sequence", "1")
        review = {"schema_version": 1, "goal_id": "goal-1", "checkpoint_id": checkpoint["checkpoint_id"], "review_id": "RV-1", "reviewed_manifest_sha256": checkpoint["manifest_sha256"], "verdict": "accepted", "criterion_decisions": [], "findings": [], "verified_commands": [], "unverified_claims": [], "next_authorized_scope": {"wp_id": "WP-1", "finding_ids": [], "allowed_paths": [], "required_tests": []}, "goal_instruction": "remain_active", "reviewed_at": "now"}
        (root / "review.json").write_text(json.dumps(review), encoding="utf-8")
        reviewed = run(root, "write-review", *common, "--checkpoint", checkpoint["checkpoint_id"], "--review", "review.json")
        ack = {"report_type": "construction_review_ack", "schema_version": 1, "review_id": "RV-1", "review_sha256": reviewed["review_sha256"], "responses": []}
        (root / "ack.json").write_text(json.dumps(ack), encoding="utf-8")
        run(root, "record-ack", *common, "--review-id", "RV-1", "--ack", "ack.json")
        run(root, "accept-checkpoint", *common, "--wp", "WP-0", "--checkpoint", checkpoint["checkpoint_id"], "--review-id", "RV-1", "--review-sha256", reviewed["review_sha256"])
        run(root, "start-run", *common, "--wp", "WP-1", "--requirement", "next", "--allow-path", "src", "--stop-condition", "review")
        blocked = subprocess.run([sys.executable, str(SCRIPT), "start-run", *common, "--wp", "WP-2", "--requirement", "skip", "--allow-path", "src", "--stop-condition", "review"], cwd=root, capture_output=True, text=True, check=False)
        assert blocked.returncode != 0 and "not authorized" in blocked.stderr
    print("construction review-gate tests passed")


if __name__ == "__main__":
    main()
