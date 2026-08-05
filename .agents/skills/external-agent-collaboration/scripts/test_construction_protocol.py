#!/usr/bin/env python3
"""Construction Goal checkpoint/review/ack state-machine regression."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("construction_protocol.py")


def run(root: Path, *args: str) -> dict:
    completed = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=root, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="construction-protocol-") as directory:
        root = Path(directory)
        (root / "scripts").mkdir()
        (root / "scripts" / "new.py").write_text("print('ok')\n", encoding="utf-8")
        contract_path = root / "goal.json"
        contract_path.write_text('{"goal_id":"goal-1","schema_version":1}\n', encoding="utf-8")
        contract_hash = hashlib.sha256(contract_path.read_bytes()).hexdigest()
        common = ["--project-root", str(root), "--goal-id", "goal-1", "--actor", "codex"]
        run(root, "init-goal", *common)
        started = run(root, "start-run", *common, "--wp", "WP-0", "--requirement", "baseline", "--allow-path", "scripts", "--stop-condition", "return Stage Report")
        report = {"report_type": "construction_stage_report", "schema_version": 1, "goal_id": "goal-1", "wp_id": "WP-0", "proposed_status": "ready_for_review", "implementation_summary": "baseline", "requirement_claims": [{"requirement_id": "baseline", "claimed_status": "passed", "claimed_evidence": ["scripts/new.py"]}], "decisions": [], "deviations": [], "commands_claimed": [], "unresolved_risks": [], "requested_review": [{"requirement_id": "baseline", "question": "check"}], "proposed_next_action": "wait_for_codex_review"}
        runtime_inputs = root / ".ai-collaboration" / "construction-inputs"
        runtime_inputs.mkdir(parents=True)
        cache = root / "scripts" / "__pycache__"
        cache.mkdir()
        (cache / "generated.cpython-314.pyc").write_bytes(b"generated-cache")
        (runtime_inputs / "report.json").write_text(json.dumps(report), encoding="utf-8")
        checkpoint = run(root, "materialize-checkpoint", *common, "--wp", "WP-0", "--report", ".ai-collaboration/construction-inputs/report.json", "--sequence", "1", "--goal-contract", "goal.json", "--goal-contract-sha256", contract_hash)
        assert checkpoint["checkpoint_id"] == "CP-001-WP-0"
        stored_checkpoint = json.loads((root / ".ai-collaboration" / "construction" / "goal-1" / "CP-001-WP-0.checkpoint.json").read_text(encoding="utf-8"))
        assert stored_checkpoint["goal_contract_sha256"] == contract_hash
        assert not any(item["path"].endswith("generated.cpython-314.pyc") for item in checkpoint.get("changed_files", []))
        validated = run(root, "validate-checkpoint", *common, "--wp", "WP-0", "--checkpoint", "CP-001-WP-0", "--status", "ready_for_review")
        assert validated["valid"] is True
        review = {"schema_version": 1, "goal_id": "goal-1", "checkpoint_id": "CP-001-WP-0", "review_id": "RV-001", "reviewed_manifest_sha256": checkpoint["manifest_sha256"], "verdict": "accepted", "criterion_decisions": [], "findings": [], "verified_commands": [], "unverified_claims": [], "next_authorized_scope": {"wp_id": "WP-1", "finding_ids": [], "allowed_paths": [], "required_tests": []}, "goal_instruction": "remain_active", "reviewed_at": "now"}
        (runtime_inputs / "review-input.json").write_text(json.dumps(review), encoding="utf-8")
        reviewed = run(root, "write-review", *common, "--checkpoint", "CP-001-WP-0", "--review", ".ai-collaboration/construction-inputs/review-input.json")
        ack = {"report_type": "construction_review_ack", "schema_version": 1, "review_id": "RV-001", "review_sha256": reviewed["review_sha256"], "responses": []}
        (runtime_inputs / "ack.json").write_text(json.dumps(ack), encoding="utf-8")
        assert run(root, "record-ack", *common, "--review-id", "RV-001", "--ack", ".ai-collaboration/construction-inputs/ack.json")["valid"] is True
        assert run(root, "accept-checkpoint", *common, "--wp", "WP-0", "--checkpoint", "CP-001-WP-0", "--review-id", "RV-001", "--review-sha256", reviewed["review_sha256"])["accepted"] is True
        assert run(root, "resume-summary", *common)["status"] == "ready_for_review"
        (root / "scripts" / "new.py").write_text("print('drifted')\n", encoding="utf-8")
        stale = subprocess.run([sys.executable, str(SCRIPT), "validate-checkpoint", *common, "--wp", "WP-0", "--checkpoint", "CP-001-WP-0"], cwd=root, capture_output=True, text=True, check=False)
        assert stale.returncode != 0 and "stale" in stale.stderr
    print("construction-protocol tests passed")


if __name__ == "__main__":
    main()
