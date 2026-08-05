#!/usr/bin/env python3
"""Trusted, read-only Antigravity consultation used by the explicit and role-router paths."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

import collaborate
from antigravity_adapter import AntigravityAdapter, AntigravityAdapterError, AntigravityInvocation
from harness_profile_support import HarnessProfileError, load_profiles, trusted
from harness_state import state_identity


def antigravity_session(key: str, sessions: list[dict], workdir: Path) -> dict:
    matches = [item for item in sessions if isinstance(item, dict) and item.get("key") == key and item.get("status") == "active" and item.get("harness") == "antigravity"]
    if len(matches) != 1 or not collaborate.session_matches_workspace(matches[0], workdir):
        raise collaborate.CollaborationError("No unique Antigravity session for this workspace; do not pass a Claude session key.")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("consult", "critique", "continue"), required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--profile", default="antigravity_readonly")
    parser.add_argument("--session-key")
    parser.add_argument("--working-directory", default=str(collaborate.PROJECT_ROOT))
    parser.add_argument("--project-root")
    parser.add_argument("--invocation-id", default=f"inv-{time.time_ns()}", help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--routing-basis", default="explicit_antigravity_entry")
    args = parser.parse_args()
    try:
        if args.timeout < 1:
            raise collaborate.CollaborationError("--timeout must be positive.")
        if args.action == "continue" and not args.session_key:
            raise collaborate.CollaborationError("Antigravity continue requires --session-key.")
        workdir = collaborate.safe_workdir(args.working_directory, args.project_root)
        path = Path(args.handoff).resolve()
        if not path.is_file() or collaborate.is_sensitive(collaborate.relative(path)):
            raise collaborate.CollaborationError("Handoff must be a readable, non-sensitive project file.")
        handoff = path.read_text(encoding="utf-8")
        collaborate.validate_handoff_sensitivity(handoff)
        profile = load_profiles(collaborate.SHARED_CONTROL_ROOT).get(args.profile)
        if not profile:
            raise HarnessProfileError(f"Harness profile '{args.profile}' is not configured.")
        if not trusted(collaborate.SHARED_CONTROL_ROOT, args.profile, profile):
            raise collaborate.CollaborationError("Antigravity profile has no current user-approved trust record. Authenticate interactively, then run trust_harness.py --profile " + args.profile + " --approve.")
        registry = collaborate.registry()
        session = antigravity_session(args.session_key, registry["sessions"], workdir) if args.session_key else None
        adapter = AntigravityAdapter()
        prompt = "You are an independent read-only reviewer. Do not edit files, run commands, invoke subagents, or access secrets.\n\n" + handoff
        invocation = AntigravityInvocation(
            launcher=str(profile.get("launcher", "agy")), prompt=prompt, workdir=workdir,
            environment=os.environ.copy(), timeout=args.timeout,
            response_schema=collaborate.RESPONSE_CONTRACT_SCHEMA, profile=profile,
            conversation_id=adapter.resume_id(session) if session else None,
        )
        code, stdout, stderr = adapter.invoke(invocation)
        if code != 0:
            detail = stderr
            terminal_status = "none"
            try:
                failed_result = adapter.parse_outer_result(stdout)
                detail += " " + str(failed_result.get("error", ""))
                terminal_status = str(failed_result.get("status", "missing"))
            except AntigravityAdapterError:
                pass
            kind = adapter.classify_error(code, detail)
            category = kind or "unclassified"
            raise collaborate.CollaborationError(f"Antigravity CLI failed before a usable response (exit={code}, status={terminal_status}, category={category}).")
        result = adapter.parse_outer_result(stdout)
        permission = adapter.permission_state({**result, "error": str(result.get("error", "")) + " " + stderr})
        response, errors = collaborate.parse_response_contract(result)
        status = "blocked_by_permission" if permission == "blocked_by_permission" else "completed" if permission == "allowed" and response is not None else "failed"
        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        output = collaborate.output_path(run_id, "outputs")
        record = {"run_id": run_id, "status": status, "harness": "antigravity", "harness_profile": args.profile, "routing": {"basis": args.routing_basis}, "topic": args.topic, "action": args.action, "permission_state": permission, "response": collaborate.redact_return_value(response) if response is not None else None, "result": collaborate.redact_return_value(result), "result_contract": {"valid": response is not None, "errors": errors}, "output_path": str(output.relative_to(collaborate.PROJECT_ROOT))}
        collaborate.write_json(output, record)
        collaborate.write_json(collaborate.output_path(run_id, "logs"), {"run_id": run_id, "status": status, "harness": "antigravity", "profile": args.profile, "routing_basis": args.routing_basis, "response_contract_valid": response is not None, "contract_errors": errors, "permission_state": permission, "finished_at": collaborate.now()})
        conversation_id = result.get("conversation_id")
        if status == "completed" and isinstance(conversation_id, str) and conversation_id:
            if session is None:
                session = {"key": f"{args.topic}-antigravity-{uuid.uuid4().hex[:6]}", "topic": args.topic, "provider": args.profile, "model_profile": args.profile, "harness": "antigravity", "harness_profile": args.profile, "working_directory": str(workdir), "workspace_identity": collaborate.workspace_identity(workdir), "host_platform": collaborate.host_platform(), "session_id": conversation_id, "external_session_id": conversation_id, "session_kind": "antigravity_conversation", "state_identity": state_identity("antigravity", args.profile, collaborate.host_platform()), "initial_toolset": ["read_only"], "status": "active", "created_at": collaborate.now()}
                registry["sessions"].append(session)
            session["last_used_at"] = collaborate.now()
            collaborate.save_registry(registry)
            topics = collaborate.topics_registry()
            collaborate.register_topic_session(topics, session)
            collaborate.write_json(collaborate.TOPICS_FILE, topics)
        print(json.dumps({"run_id": run_id, "status": status, "harness": "antigravity", "routing": {"basis": args.routing_basis}, "output_path": str(output.relative_to(collaborate.PROJECT_ROOT)), "result_contract_failed": response is None}, ensure_ascii=False, indent=2))
        return 0 if status == "completed" else 3
    except (collaborate.CollaborationError, HarnessProfileError, AntigravityAdapterError) as exc:
        try:
            from failure_events import write_failure_event
            write_failure_event(collaborate.CONTEXT, invocation_id=args.invocation_id, error_code="response_contract_failed" if "response" in str(exc).lower() else "provider_unclassified_failure", stage="antigravity_consult", selected_harness="antigravity", action=args.action, mode="analyze", message=str(exc), working_directory=args.working_directory)
        except Exception:
            pass
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
