"""Privacy-safe, exactly-once failure events for public Skill entrypoints."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspace_context import WorkspaceContext
from version import SKILL_RUNTIME_VERSION


SCHEMA_VERSION = 1
REDACTION_VERSION = "failure-event-v1"
ERROR_METADATA = {
    "invalid_arguments": ("input", False, "fix_arguments"),
    "skill_project_root_unavailable": ("installation", False, "restore_source_link_installation"),
    "cross_project_context_unsupported": ("workspace", False, "upgrade_workspace_context"),
    "project_root_required_for_non_git_workspace": ("workspace", False, "fix_workspace_context"),
    "project_root_git_root_conflict": ("workspace", False, "fix_workspace_context"),
    "project_root_not_directory": ("workspace", False, "fix_workspace_context"),
    "target_workdir_outside_project": ("workspace", False, "fix_workspace_context"),
    "target_control_root_unwritable": ("filesystem", False, "make_target_runtime_writable"),
    "handoff_outside_project": ("input", False, "relocate_or_create_handoff"),
    "handoff_missing_or_unreadable": ("input", False, "relocate_or_create_handoff"),
    "classification_route_mismatch": ("internal", False, "repair_classification_contract"),
    "handoff_sensitive": ("safety", False, "redact_or_use_native_codex"),
    "classification_prohibited": ("safety", False, "redact_or_use_native_codex"),
    "classification_requires_redaction": ("safety", False, "redact_or_use_native_codex"),
    "provider_profile_missing": ("configuration", False, "configure_local_profile"),
    "provider_trust_missing_or_stale": ("trust", False, "refresh_non_secret_trust"),
    "harness_not_ready": ("readiness", False, "repair_requested_harness"),
    "harness_profile_missing": ("configuration", False, "configure_local_profile"),
    "harness_trust_missing_or_stale": ("trust", False, "refresh_non_secret_trust"),
    "session_not_found": ("session", False, "start_new_session"),
    "session_workspace_mismatch": ("session", False, "start_new_session"),
    "ambiguous_cross_harness_session": ("session", False, "pass_exact_session_key"),
    "no_eligible_provider": ("routing", False, "fix_routing_configuration"),
    "no_healthy_provider": ("availability", True, "retry_after_health_cooldown"),
    "linked_path_in_execute_scope": ("safety", False, "reduce_or_repair_scope"),
    "scope_guard_unavailable": ("readiness", False, "repair_scope_guard"),
    "scope_guard_protocol_invalid": ("readiness", False, "repair_scope_guard"),
    "scope_guard_denied": ("safety", False, "reduce_or_repair_scope"),
    "checkpoint_failed": ("filesystem", False, "repair_checkpoint_precondition"),
    "child_process_launch_failed": ("host", False, "repair_launcher"),
    "child_process_unclassified": ("protocol", False, "inspect_local_run_output"),
    "provider_timeout": ("availability", True, "retry_once_with_backoff"),
    "provider_rate_limited": ("availability", True, "retry_once_with_backoff"),
    "provider_transport_failed": ("availability", True, "retry_once_with_backoff"),
    "provider_unclassified_failure": ("protocol", False, "inspect_local_run_output"),
    "provider_authentication_failed": ("account", False, "authenticate_provider"),
    "provider_billing_failed": ("account", False, "repair_provider_billing"),
    "permission_blocked": ("permission", False, "adjust_approved_profile_or_scope"),
    "response_parsing_failed": ("protocol", False, "repair_response_contract"),
    "response_contract_failed": ("protocol", False, "repair_response_contract"),
    "construction_stage_report_invalid": ("protocol", False, "repair_construction_response"),
    "construction_checkpoint_stale": ("state", False, "regenerate_checkpoint_from_current_workspace"),
    "construction_review_ack_invalid": ("protocol", False, "repair_construction_response"),
    "construction_wp_not_authorized": ("governance", False, "complete_current_codex_review_gate"),
    "expected_outcome_failed": ("validation", False, "review_and_start_new_bounded_run"),
    "validation_failed": ("validation", False, "review_and_start_new_bounded_run"),
    "scope_violation": ("safety", False, "reduce_or_repair_scope"),
    "goal_persistence_failed": ("state", False, "repair_local_state_then_resume_explicitly"),
    "state_lock_timeout": ("state", True, "retry_state_write_once"),
    "state_lock_unsupported": ("state", False, "use_supported_local_filesystem"),
    "state_persistence_failed": ("state", False, "repair_local_state_then_resume_explicitly"),
    "rollback_failed": ("rollback", False, "perform_manual_recovery"),
    "budget_exhausted": ("budget", False, "raise_budget_explicitly_or_stop"),
    "cancelled_by_host": ("host", True, "restart_only_if_still_requested"),
    "unexpected_internal_error": ("internal", False, "analyze_bad_case_before_retry"),
}
ERROR_CODES = frozenset(ERROR_METADATA)
TERMINAL_STATUSES = frozenset({"failed_preflight", "failed_invocation", "blocked_by_permission", "failed_validation", "rolled_back", "rollback_failed", "cancelled_by_host"})
STAGES = frozenset({"argument_parsing", "workspace_resolution", "handoff_validation", "classification", "routing", "trust", "readiness", "invocation", "response_parsing", "scope_validation", "outcome_validation", "rollback", "state_persistence", "unexpected"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def _safe_text(value: Any, limit: int = 240) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    text = re.sub(r"(?<![A-Za-z0-9_.])/(?:[^\s/]+/)*[^\s]+", "[PATH]", text)
    text = re.sub(r"\b[A-Za-z]:\\[^\s]+", "[PATH]", text)
    text = re.sub(r"\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_\-]{12,}\b", "[REDACTED_SECRET]", text, flags=re.IGNORECASE)
    return text[:limit]


def _relative_or_hash(context: WorkspaceContext | None, value: Any) -> str | None:
    if value is None:
        return None
    try:
        if context is not None:
            path = Path(str(value))
            if path.is_absolute():
                try:
                    return context.target_relative(path).as_posix()
                except Exception:
                    try:
                        return "skill:" + context.skill_relative(path).as_posix()
                    except Exception:
                        return "path-hash:" + _sha(os.path.normcase(os.path.normpath(os.fspath(path))))[:16]
    except Exception:
        pass
    return _safe_text(value)


def _skill_revision(context: WorkspaceContext | None) -> tuple[str | None, bool | None]:
    if context is None:
        return None, None
    try:
        result = subprocess.run(["git", "-C", str(context.skill_project_root), "rev-parse", "HEAD"], capture_output=True, text=True, shell=False, check=False, timeout=5)
        revision = result.stdout.strip()
        status = subprocess.run(["git", "-C", str(context.skill_project_root), "status", "--porcelain"], capture_output=True, text=True, shell=False, check=False, timeout=5)
        if len(revision) == 40 and all(char in "0123456789abcdef" for char in revision.lower()):
            return revision, bool(status.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return f"runtime:{SKILL_RUNTIME_VERSION}", None


def event_path(context: WorkspaceContext, invocation_id: str) -> Path:
    return context.failure_ledger_root / f"{invocation_id}.json"


def write_failure_event(
    context: WorkspaceContext | None,
    *,
    invocation_id: str,
    terminal_status: str = "failed",
    stage: str = "unknown",
    error_code: str = "unexpected_internal_error",
    error_category: str | None = None,
    retryable: bool | None = None,
    next_action: str | None = None,
    provider_invoked: bool = False,
    requested_harness: str | None = None,
    selected_harness: str | None = None,
    requested_provider: str | None = None,
    selected_provider: str | None = None,
    route_basis: str | None = None,
    action: str | None = None,
    task_type: str | None = None,
    mode: str | None = None,
    workspace_hash: str | None = None,
    handoff_sha256: str | None = None,
    handoff_bytes: int | None = None,
    skill_revision: str | None = None,
    dirty_before: bool | None = None,
    run_id: str | None = None,
    child_exit_code: int | None = None,
    duration_seconds: float | None = None,
    rollback_attempted: bool = False,
    rollback_succeeded: bool | None = None,
    message: str | None = None,
    working_directory: str | None = None,
    parent_invocation_id: str | None = None,
) -> Path | None:
    if context is None:
        return None
    if not invocation_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for char in invocation_id):
        return None
    if error_code not in ERROR_CODES:
        error_code = "unexpected_internal_error"
    if terminal_status not in TERMINAL_STATUSES:
        terminal_status = "failed_invocation"
    if stage not in STAGES:
        stage = "unexpected"
    metadata_category, metadata_retryable, metadata_next_action = ERROR_METADATA[error_code]
    skill_revision, skill_dirty = _skill_revision(context)
    path = event_path(context, invocation_id)
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "invocation_id": invocation_id,
        "parent_invocation_id": parent_invocation_id,
        "occurred_at": _utc_now(),
        "terminal_status": terminal_status,
        "stage": stage,
        "error_code": error_code,
        "error_category": error_category or metadata_category,
        "retryable": metadata_retryable if retryable is None else bool(retryable),
        "next_action": next_action or metadata_next_action,
        "provider_invoked": bool(provider_invoked),
        "requested_harness": requested_harness,
        "selected_harness": selected_harness,
        "requested_provider": requested_provider,
        "selected_provider": selected_provider,
        "route_basis": route_basis,
        "action": action,
        "task_type": task_type,
        "mode": mode,
        "host_platform": "windows" if os.name == "nt" else "macos" if sys.platform == "darwin" else "linux",
        "path_style": "windows" if os.name == "nt" else "posix",
        "workspace_hash": workspace_hash or (context.workspace_hash if context else None),
        "handoff_sha256": handoff_sha256,
        "handoff_bytes": handoff_bytes,
        "skill_revision": skill_revision,
        "skill_runtime_version": SKILL_RUNTIME_VERSION,
        "skill_dirty": skill_dirty,
        "dirty_before": dirty_before,
        "run_id": run_id,
        "child_exit_code": child_exit_code,
        "duration_seconds": duration_seconds,
        "duration_ms": round(duration_seconds * 1000) if duration_seconds is not None else None,
        "rollback_attempted": rollback_attempted,
        "rollback_succeeded": rollback_succeeded,
        "message": _safe_text(message),
        "working_directory": _relative_or_hash(context, working_directory),
        "redaction_version": REDACTION_VERSION,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{invocation_id}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
