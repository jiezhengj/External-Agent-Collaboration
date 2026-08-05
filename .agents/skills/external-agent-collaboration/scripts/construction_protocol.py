#!/usr/bin/env python3
"""Codex-owned construction Goal/checkpoint/review protocol.

Luna only returns the two documented response objects.  This module is the
runner-owned control plane: it writes runtime state, independently hashes the
workspace, validates handoffs, and creates accepted markers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from failure_events import write_failure_event
from state_store import StateStoreError, locked, load, save
from workspace_context import WorkspaceContextError, link_like, resolve_context


SCHEMA_VERSION = 1
REPORT_TYPES = {"construction_stage_report"}
REPORT_STATUSES = {"ready_for_review", "in_progress_interrupted", "blocked"}
CHECKPOINT_STATUSES = REPORT_STATUSES
REVIEW_VERDICTS = {"accepted", "accepted_with_followups", "changes_required", "blocked", "failed"}
ACK_STATUSES = {"accepted", "completed", "disputed", "blocked"}
SENSITIVE_PARTS = {".git", ".ai-collaboration", "secrets", "credentials", "private"}


class ConstructionError(ValueError):
    def __init__(self, message: str, code: str = "construction_stage_report_invalid") -> None:
        super().__init__(message)
        self.code = code


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_id(value: str, label: str) -> str:
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for char in value):
        raise ConstructionError(f"{label} is invalid")
    return value


def runtime_dir(project_root: Path, goal_id: str) -> Path:
    safe_id(goal_id, "goal_id")
    return project_root / ".ai-collaboration" / "construction" / goal_id


def _wp_number(wp: str) -> int:
    if not wp.startswith("WP-") or not wp[3:].isdigit():
        raise ConstructionError("wp must use WP-<number> format", "construction_wp_not_authorized")
    number = int(wp[3:])
    if number < 0 or number > 7:
        raise ConstructionError("wp must be between WP-0 and WP-7", "construction_wp_not_authorized")
    return number


def relative_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or any(part in SENSITIVE_PARTS or part.startswith(".env") for part in path.parts):
        raise ConstructionError("path must be a non-sensitive project-relative path")
    candidate = root / path
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ConstructionError("path escapes project root") from exc
    return path


def walk_files(root: Path) -> list[Path]:
    result: list[Path] = []
    pending = [root]
    while pending:
        current = pending.pop()
        for entry in os.scandir(current):
            path = Path(entry.path)
            rel = path.relative_to(root)
            if rel.parts and rel.parts[0] in SENSITIVE_PARTS:
                continue
            if entry.is_dir(follow_symlinks=False) and not link_like(path):
                pending.append(path)
            elif entry.is_file(follow_symlinks=False) or link_like(path):
                result.append(path)
    return sorted(result, key=lambda item: item.relative_to(root).as_posix())


def workspace_manifest(root: Path, base_revision: str | None = None, exclude_paths: set[str] | None = None) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    excluded = exclude_paths or set()
    for path in walk_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in excluded:
            continue
        if link_like(path):
            files.append({"path": rel, "git_state": "unknown", "kind": "link_leaf", "size": 0, "sha256": sha256_bytes(os.readlink(path).encode("utf-8", "surrogatepass"))})
            continue
        data = path.read_bytes()
        files.append({"path": rel, "git_state": "unknown", "kind": "regular_file", "size": len(data), "sha256": sha256_bytes(data)})
    payload = {"schema_version": 1, "base_revision": base_revision or git_revision(root), "generated_at": now(), "files": files}
    digest_payload = {"schema_version": payload["schema_version"], "base_revision": payload["base_revision"], "files": payload["files"]}
    payload["manifest_sha256"] = sha256_bytes(json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return payload


def git_revision(root: Path) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, shell=False, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "0" * 40
    value = result.stdout.strip()
    return value if len(value) == 40 else "0" * 40


def git_dirty_paths(root: Path) -> list[str]:
    try:
        result = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, shell=False, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        raw = line[3:]
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1]
        try:
            relative_path(root, raw)
        except ConstructionError:
            continue
        paths.append(Path(raw).as_posix())
    return sorted(set(paths))


def read_project_json(root: Path, value: str) -> tuple[Path, dict[str, Any]]:
    path = root / relative_path(root, value)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConstructionError(f"cannot read JSON artifact: {value}") from exc
    if not isinstance(data, dict):
        raise ConstructionError("JSON artifact must be an object")
    return path, data


def write_runtime(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save(path, value)


def write_runtime_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_report(report: Any, goal_id: str, wp: str, root: Path | None = None) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("report_type") not in REPORT_TYPES or report.get("schema_version") != 1:
        raise ConstructionError("invalid construction_stage_report")
    if report.get("goal_id") != goal_id or report.get("wp_id") != wp:
        raise ConstructionError("Stage Report goal_id/wp_id does not match the active run")
    if report.get("proposed_status") not in REPORT_STATUSES:
        raise ConstructionError("Stage Report proposed_status is invalid")
    for key in ("implementation_summary", "proposed_next_action"):
        if not isinstance(report.get(key), str) or len(report[key]) > 1000:
            raise ConstructionError(f"Stage Report {key} is invalid")
    claims = report.get("requirement_claims", [])
    if not isinstance(claims, list):
        raise ConstructionError("requirement_claims must be an array")
    if report["proposed_status"] == "ready_for_review" and (not claims or any(isinstance(item, dict) and item.get("claimed_status") == "pending" for item in claims)):
        raise ConstructionError("ready_for_review requires non-pending requirement claims")
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("requirement_id"), str) or claim.get("claimed_status") not in {"passed", "failed", "pending", "not_applicable"}:
            raise ConstructionError("invalid requirement claim")
        for evidence in claim.get("claimed_evidence", []):
            relative_path(root or Path.cwd(), evidence)
    for key in ("decisions", "deviations", "commands_claimed", "unresolved_risks", "requested_review"):
        if not isinstance(report.get(key, []), list):
            raise ConstructionError(f"{key} must be an array")
    for risk in report.get("unresolved_risks", []):
        if isinstance(risk, dict) and risk.get("priority") in {"P0", "P1"} and report["proposed_status"] == "ready_for_review":
            raise ConstructionError("ready_for_review cannot contain unresolved P0/P1 risk")
    if report["proposed_status"] == "blocked" and not report.get("unresolved_risks"):
        raise ConstructionError("blocked Stage Report requires a blocker/risk evidence")
    return report


def validate_checkpoint(checkpoint: Any, goal_id: str, wp: str, status: str | None = None, root: Path | None = None) -> dict[str, Any]:
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != 1:
        raise ConstructionError("invalid checkpoint schema")
    if checkpoint.get("goal_id") != goal_id or checkpoint.get("wp_id") != wp:
        raise ConstructionError("checkpoint goal_id/wp_id mismatch")
    if checkpoint.get("status") not in CHECKPOINT_STATUSES:
        raise ConstructionError("checkpoint status is invalid")
    if status and checkpoint.get("status") != status:
        raise ConstructionError("checkpoint status does not match expected status")
    if not isinstance(checkpoint.get("changed_files"), list) or not isinstance(checkpoint.get("requirement_results"), list):
        raise ConstructionError("checkpoint mapping arrays are required")
    for item in checkpoint["changed_files"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ConstructionError("checkpoint changed_files entry is invalid")
        relative_path(root or Path.cwd(), item["path"])
    for item in checkpoint["requirement_results"]:
        if not isinstance(item, dict) or item.get("status") not in {"passed", "failed", "pending", "not_applicable"}:
            raise ConstructionError("checkpoint requirement result is invalid")
    return checkpoint


def validate_review(review: Any, goal_id: str, checkpoint_id: str) -> dict[str, Any]:
    if not isinstance(review, dict) or review.get("schema_version") != 1 or review.get("goal_id") != goal_id or review.get("checkpoint_id") != checkpoint_id:
        raise ConstructionError("invalid construction review")
    if review.get("verdict") not in REVIEW_VERDICTS:
        raise ConstructionError("review verdict is invalid")
    findings = review.get("findings")
    if not isinstance(findings, list):
        raise ConstructionError("review findings must be an array")
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("priority") not in {"P0", "P1", "P2"} or not isinstance(finding.get("finding_id"), str) or not isinstance(finding.get("required_change"), str) or not isinstance(finding.get("acceptance_test"), str):
            raise ConstructionError("review finding must include priority, required_change and acceptance_test")
        if finding.get("path") is not None:
            relative_path(Path.cwd(), str(finding["path"]))
    if review["verdict"] in {"accepted", "accepted_with_followups"} and any(item.get("blocking") or (review["verdict"] == "accepted_with_followups" and item.get("priority") in {"P0", "P1"}) for item in findings):
        raise ConstructionError("accepted review cannot contain blocking findings")
    return review


def validate_ack(ack: Any, review: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(ack, dict) or ack.get("report_type") != "construction_review_ack" or ack.get("schema_version") != 1:
        raise ConstructionError("invalid construction_review_ack")
    review_hash = sha256_bytes(json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if ack.get("review_sha256") != review_hash:
        raise ConstructionError("review hash mismatch")
    expected = {item["finding_id"] for item in review.get("findings", [])}
    responses = ack.get("responses")
    response_ids = [item.get("finding_id") for item in responses if isinstance(item, dict)] if isinstance(responses, list) else []
    if not isinstance(responses, list) or len(response_ids) != len(set(response_ids)) or set(response_ids) != expected:
        raise ConstructionError("acknowledgement must cover every review finding exactly once")
    if any(not isinstance(item, dict) or item.get("status") not in ACK_STATUSES for item in responses):
        raise ConstructionError("acknowledgement status is invalid")
    return ack


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    directory = runtime_dir(root, args.goal_id)
    directory.mkdir(parents=True, exist_ok=True)
    current = {"schema_version": 1, "goal_id": args.goal_id, "status": "active", "wp_id": None, "run_id": None, "current_requirement": None, "authorized_paths": [], "authorized_commands": [], "pre_run_manifest_sha256": None, "recent_evidence_ids": [], "next_action": "start WP-0", "updated_at": now()}
    with locked(directory / "current.json"):
        if not (directory / "current.json").exists():
            write_runtime(directory / "current.json", current)
    print(json.dumps({"goal_id": args.goal_id, "runtime": str(directory.relative_to(root)), "status": "active"}, ensure_ascii=False))
    return 0


def cmd_start_run(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    directory = runtime_dir(root, args.goal_id)
    directory.mkdir(parents=True, exist_ok=True)
    number = _wp_number(args.wp)
    manifest = workspace_manifest(root)
    run_id = args.run_id or f"run-{uuid.uuid4().hex[:12]}"
    previous = load(directory / "current.json", {})
    attempts = int(previous.get("attempts", 0)) if isinstance(previous, dict) else 0
    if attempts >= 32:
        raise ConstructionError("construction attempt limit of 32 reached", "construction_wp_not_authorized")
    if number > 0 and not (directory / f"WP-{number - 1}.accepted").is_file():
        raise ConstructionError(f"{args.wp} is not authorized before WP-{number - 1}.accepted", "construction_wp_not_authorized")
    current = {"schema_version": 1, "goal_id": args.goal_id, "wp_id": args.wp, "run_id": run_id, "status": "running", "attempts": attempts + 1, "current_requirement": args.requirement, "authorized_paths": [relative_path(root, item).as_posix() for item in args.allow_path], "authorized_commands": args.allow_command, "pre_run_manifest_sha256": manifest["manifest_sha256"], "user_dirty_paths": git_dirty_paths(root), "recent_evidence_ids": [], "next_action": args.stop_condition, "updated_at": now()}
    with locked(directory / "current.json"):
        write_runtime(directory / "current.json", current)
        write_runtime(directory / f"pre-{run_id}.workspace-manifest.json", manifest)
    print(json.dumps({"run_id": run_id, "pre_run_manifest_sha256": manifest["manifest_sha256"]}, ensure_ascii=False))
    return 0


def cmd_materialize(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    directory = runtime_dir(root, args.goal_id)
    report_path, report = read_project_json(root, args.report)
    validate_report(report, args.goal_id, args.wp, root)
    current = load(directory / "current.json", {})
    run_id = current.get("run_id") or args.run_id
    manifest = workspace_manifest(root)
    pre = load(directory / f"pre-{run_id}.workspace-manifest.json", {})
    before = {item.get("path"): item for item in pre.get("files", []) if isinstance(item, dict)}
    after = {item.get("path"): item for item in manifest.get("files", []) if isinstance(item, dict)}
    dirty = set(current.get("user_dirty_paths", []))
    checkpoint_id = f"CP-{int(args.sequence):03d}-{args.wp}"
    changed = []
    for path in sorted(set(before) | set(after)):
        if before.get(path, {}).get("sha256") == after.get(path, {}).get("sha256") and path in before and path in after:
            continue
        if path not in before:
            change_type = "added"
        elif path not in after:
            change_type = "deleted"
        else:
            change_type = "modified"
        changed.append({"path": path, "change_type": change_type, "sha256": after.get(path, {}).get("sha256"), "requirement_ids": [], "reason": "runner observed post-run workspace", "risk": "unknown", "owned_by_current_run": path not in dirty})
    checkpoint = {"schema_version": 1, "goal_id": args.goal_id, "checkpoint_id": checkpoint_id, "wp_id": args.wp, "run_id": run_id, "status": report["proposed_status"], "created_at": now(), "base_revision": git_revision(root), "goal_contract_sha256": args.goal_contract_sha256, "implementation_summary": report["implementation_summary"], "requirement_results": [{"requirement_id": item["requirement_id"], "status": item["claimed_status"], "evidence_ids": item.get("claimed_evidence", [])} for item in report["requirement_claims"]], "changed_files": changed, "decisions": report.get("decisions", []), "deviations": report.get("deviations", []), "unresolved_risks": report.get("unresolved_risks", []), "requested_review": report.get("requested_review", []), "proposed_next_wp": args.next_wp, "manifest_sha256": manifest["manifest_sha256"], "report_path": str(report_path.relative_to(root))}
    validate_checkpoint(checkpoint, args.goal_id, args.wp, root=root)
    with locked(directory / "current.json"):
        write_runtime(directory / f"{checkpoint_id}.checkpoint.json", checkpoint)
        write_runtime(directory / "workspace-manifest.json", manifest)
        evidence = []
        for index, command in enumerate(report.get("commands_claimed", []), 1):
            if isinstance(command, str):
                evidence.append({"evidence_id": f"CLAIM-{index:03d}", "kind": "model_claim", "platform": "windows" if os.name == "nt" else "macos", "argv": [command], "working_directory": ".", "exit_code": None, "duration_ms": None, "result": "unverified", "output_sha256": None, "bounded_summary": "Luna claimed command; runner did not observe execution", "artifact_paths": []})
        write_runtime(directory / "evidence.json", evidence)
        handoff_lines = ["# Construction handoff", "", f"- Goal: {args.goal_id}", f"- WP: {args.wp}", f"- Checkpoint: {checkpoint_id}", "", "## Luna claim", report["implementation_summary"], "", "## Runner-observed changes"]
        handoff_lines.extend(f"- {item['change_type']}: {item['path']} (owned_by_current_run={item.get('owned_by_current_run', False)})" for item in changed)
        handoff_lines.extend(["", "## Unresolved risks", *[f"- {item}" for item in report.get("unresolved_risks", [])], "", "## Requested Codex review", *[f"- {item}" for item in report.get("requested_review", [])]])
        write_runtime_text(directory / "handoff.md", "\n".join(handoff_lines[:120]) + "\n")
        current.update({"status": report["proposed_status"], "checkpoint_id": checkpoint_id, "recent_evidence_ids": [item.get("evidence_id") for item in report.get("evidence", []) if isinstance(item, dict)], "next_action": "wait_for_codex_review", "updated_at": now()})
        write_runtime(directory / "current.json", current)
    print(json.dumps({"checkpoint_id": checkpoint_id, "manifest_sha256": manifest["manifest_sha256"]}, ensure_ascii=False))
    return 0


def cmd_validate_checkpoint(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    directory = runtime_dir(root, args.goal_id)
    path = directory / f"{args.checkpoint}.checkpoint.json" if args.checkpoint else directory / "checkpoint.json"
    checkpoint = load(path, None)
    validate_checkpoint(checkpoint, args.goal_id, args.wp, args.status, root)
    current_manifest = workspace_manifest(root)
    if checkpoint.get("manifest_sha256") != current_manifest.get("manifest_sha256"):
        raise ConstructionError("checkpoint is stale: workspace manifest changed", "construction_checkpoint_stale")
    print(json.dumps({"valid": True, "checkpoint_id": checkpoint["checkpoint_id"], "manifest_sha256": checkpoint.get("manifest_sha256")}, ensure_ascii=False))
    return 0


def cmd_write_review(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    directory = runtime_dir(root, args.goal_id)
    path, review = read_project_json(root, args.review)
    validate_review(review, args.goal_id, args.checkpoint)
    review["runner_review_source"] = str(path.relative_to(root))
    checkpoint = load(directory / f"{args.checkpoint}.checkpoint.json", None)
    validate_checkpoint(checkpoint, args.goal_id, str(checkpoint.get("wp_id")), root=root)
    if review.get("reviewed_manifest_sha256") != checkpoint.get("manifest_sha256"):
        raise ConstructionError("review manifest does not match checkpoint")
    if workspace_manifest(root, exclude_paths={str(path.relative_to(root))}).get("manifest_sha256") != checkpoint.get("manifest_sha256"):
        raise ConstructionError("review is stale: workspace manifest changed", "construction_checkpoint_stale")
    with locked(directory / "current.json"):
        write_runtime(directory / f"{review['review_id']}.review.json", review)
        if args.markdown:
            (directory / f"{review['review_id']}.review.md").write_text(Path(args.markdown).read_text(encoding="utf-8")[:12000], encoding="utf-8")
    print(json.dumps({"review_id": review["review_id"], "verdict": review["verdict"], "review_sha256": sha256_bytes(json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))}, ensure_ascii=False))
    return 0


def cmd_record_ack(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    directory = runtime_dir(root, args.goal_id)
    review = load(directory / f"{args.review_id}.review.json", None)
    ack_path, ack = read_project_json(root, args.ack)
    validate_ack(ack, review)
    ack["runner_ack_source"] = str(ack_path.relative_to(root))
    with locked(directory / "current.json"):
        write_runtime(directory / f"{args.review_id}.acknowledgement.json", ack)
    print(json.dumps({"review_id": args.review_id, "valid": True, "ack_path": str(ack_path.relative_to(root))}, ensure_ascii=False))
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    directory = runtime_dir(root, args.goal_id)
    review = load(directory / f"{args.review_id}.review.json", None)
    validate_review(review, args.goal_id, args.checkpoint)
    if review.get("verdict") != "accepted" or any(item.get("blocking") for item in review.get("findings", [])):
        raise ConstructionError("checkpoint cannot be accepted")
    digest = sha256_bytes(json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if args.review_sha256 != digest:
        raise ConstructionError("review hash mismatch")
    ack = load(directory / f"{args.review_id}.acknowledgement.json", None)
    validate_ack(ack, review)
    if any(item.get("status") not in {"accepted", "completed"} for item in ack.get("responses", [])):
        raise ConstructionError("checkpoint cannot be accepted with unaccepted finding responses")
    excluded = {item for item in (review.get("runner_review_source"), ack.get("runner_ack_source")) if isinstance(item, str)}
    if workspace_manifest(root, exclude_paths=excluded).get("manifest_sha256") != load(directory / f"{args.checkpoint}.checkpoint.json", {}).get("manifest_sha256"):
        raise ConstructionError("checkpoint is stale: workspace changed during review", "construction_checkpoint_stale")
    marker = {"checkpoint_id": args.checkpoint, "review_sha256": digest, "accepted_at": now(), "actor": "codex"}
    with locked(directory / "current.json"):
        write_runtime(directory / f"{args.wp}.accepted", marker)
    print(json.dumps({"accepted": True, "checkpoint_id": args.checkpoint}, ensure_ascii=False))
    return 0


def cmd_interrupt(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    directory = runtime_dir(root, args.goal_id)
    current = load(directory / "current.json", None)
    if not isinstance(current, dict):
        raise ConstructionError("current run does not exist")
    current.update({"status": "in_progress_interrupted", "next_action": args.next_action, "updated_at": now()})
    with locked(directory / "current.json"):
        write_runtime(directory / "current.json", current)
    print(json.dumps({"status": current["status"], "next_action": current["next_action"]}, ensure_ascii=False))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    directory = runtime_dir(root, args.goal_id)
    current = load(directory / "current.json", None)
    if not isinstance(current, dict):
        raise ConstructionError("no resumable construction state")
    manifest = workspace_manifest(root)
    summary = f"Goal {args.goal_id}, {current.get('wp_id') or 'no WP'}, status {current.get('status')}; current manifest {manifest['manifest_sha256']}; next action: {current.get('next_action')}"
    resume = directory / "resume" / "latest.md"
    resume.parent.mkdir(parents=True, exist_ok=True)
    resume.write_text("# Construction resume\n\n" + summary + "\n", encoding="utf-8")
    print(json.dumps({"status": current.get("status"), "next_action": current.get("next_action"), "resume_path": str(resume.relative_to(root))}, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    def common(command: str) -> argparse.ArgumentParser:
        child = sub.add_parser(command)
        child.add_argument("--project-root", required=True)
        child.add_argument("--goal-id", required=True)
        child.add_argument("--actor", required=True, choices=("codex",))
        return child
    common("init-goal")
    start = common("start-run"); start.add_argument("--wp", required=True); start.add_argument("--requirement", required=True); start.add_argument("--allow-path", action="append", default=[]); start.add_argument("--allow-command", action="append", default=[]); start.add_argument("--stop-condition", required=True); start.add_argument("--run-id")
    materialize = common("materialize-checkpoint"); materialize.add_argument("--wp", required=True); materialize.add_argument("--report", required=True); materialize.add_argument("--sequence", required=True, type=int); materialize.add_argument("--next-wp"); materialize.add_argument("--run-id"); materialize.add_argument("--goal-contract-sha256", default=None)
    validate = common("validate-checkpoint"); validate.add_argument("--wp", required=True); validate.add_argument("--checkpoint"); validate.add_argument("--status")
    review = common("write-review"); review.add_argument("--checkpoint", required=True); review.add_argument("--review", required=True); review.add_argument("--markdown")
    ack = common("record-ack"); ack.add_argument("--review-id", required=True); ack.add_argument("--ack", required=True)
    accept = common("accept-checkpoint"); accept.add_argument("--wp", required=True); accept.add_argument("--checkpoint", required=True); accept.add_argument("--review-id", required=True); accept.add_argument("--review-sha256", required=True)
    interrupt = common("interrupt-run"); interrupt.add_argument("--next-action", required=True)
    common("resume-summary")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        root = Path(args.project_root).resolve()
        if not root.is_dir():
            raise ConstructionError("project root is not a directory")
        handlers = {"init-goal": cmd_init, "start-run": cmd_start_run, "materialize-checkpoint": cmd_materialize, "validate-checkpoint": cmd_validate_checkpoint, "write-review": cmd_write_review, "record-ack": cmd_record_ack, "accept-checkpoint": cmd_accept, "interrupt-run": cmd_interrupt, "resume-summary": cmd_resume}
        return handlers[args.command](args)
    except (ConstructionError, OSError, StateStoreError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
