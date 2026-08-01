#!/usr/bin/env python3
"""Bounded Antigravity P3 execute runner with manifest rollback."""

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


def scope_allows(requested: list[Path], configured: list[str]) -> bool:
    return all(collaborate.allowed(path, [Path(value) for value in configured]) for path in requested)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--expected-outcomes", required=True)
    parser.add_argument("--allow-path", action="append", required=True)
    parser.add_argument("--allow-command", action="append", default=[])
    parser.add_argument("--validation-command", action="append", default=[])
    parser.add_argument("--profile", default="antigravity_execute")
    parser.add_argument("--working-directory", default=str(collaborate.PROJECT_ROOT))
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    try:
        if args.timeout < 1:
            raise collaborate.CollaborationError("--timeout must be positive.")
        workdir = collaborate.safe_workdir(args.working_directory)
        handoff_path = Path(args.handoff).resolve()
        if not handoff_path.is_file() or collaborate.is_sensitive(collaborate.relative(handoff_path)):
            raise collaborate.CollaborationError("Handoff must be a readable, non-sensitive project file.")
        handoff = handoff_path.read_text(encoding="utf-8")
        collaborate.validate_handoff_sensitivity(handoff)
        allow_paths = [collaborate.normalize_allow_path(item) for item in args.allow_path]
        outcomes = collaborate.load_outcomes(Path(args.expected_outcomes).resolve())
        profile = load_profiles(collaborate.CONTROL_ROOT).get(args.profile)
        if not profile or profile.get("mode") != "accept-edits":
            raise collaborate.CollaborationError("P3 execute requires a trusted Antigravity accept-edits profile.")
        if not trusted(collaborate.CONTROL_ROOT, args.profile, profile):
            raise collaborate.CollaborationError("Antigravity execute profile has no current trust record.")
        scope = profile["execution_scope"]
        configured_paths = scope["allowed_paths"]
        configured_commands = scope["allowed_commands"]
        if not scope_allows(allow_paths, configured_paths):
            raise collaborate.CollaborationError("Requested paths exceed the trusted Antigravity execution scope.")
        if any(command not in configured_commands for command in args.allow_command + args.validation_command):
            raise collaborate.CollaborationError("Requested commands exceed the trusted Antigravity execution scope.")
        adapter = AntigravityAdapter()
        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        checkpoint = collaborate.copy_checkpoint(run_id)
        before = collaborate.manifest(collaborate.PROJECT_ROOT)
        prompt = f"""You are a bounded project executor. Edit only: {', '.join(path.as_posix() for path in allow_paths)}.
Allowed commands: {', '.join(args.allow_command) or '(none)'}.
Never access protected material, commit, push, deploy, publish, install software, or use an unlisted command.
Return this JSON contract only:\n{collaborate.response_contract_instruction('compact', 'standard')}\n\nHandoff:\n{handoff}"""
        code, stdout, stderr = adapter.invoke(AntigravityInvocation(str(profile.get("launcher", "agy")), prompt, workdir, os.environ.copy(), args.timeout, collaborate.RESPONSE_CONTRACT_SCHEMA, profile))
        if code != 0:
            raise collaborate.CollaborationError(f"Antigravity execute failed before a usable response (exit={code}, category={adapter.classify_error(code, stderr) or 'unclassified'}).")
        result = adapter.parse_outer_result(stdout)
        permission = adapter.permission_state({**result, "error": str(result.get("error", "")) + " " + stderr})
        response, errors = collaborate.parse_response_contract(result)
        after = collaborate.manifest(collaborate.PROJECT_ROOT)
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        violations = [path for path in changed if collaborate.is_sensitive(Path(path)) or not collaborate.allowed(Path(path), allow_paths)]
        outcome_results = collaborate.evaluate_outcomes(outcomes, changed, workdir, args.validation_command)
        failed = permission != "allowed" or response is None or bool(violations) or any(not item.get("passed") for item in outcome_results)
        if failed:
            collaborate.restore_changed(before, collaborate.manifest(collaborate.PROJECT_ROOT), checkpoint)
        status = "blocked_by_permission" if permission == "blocked_by_permission" else "failed" if failed else "completed"
        output = collaborate.output_path(run_id, "outputs")
        record = {"run_id": run_id, "status": status, "harness": "antigravity", "harness_profile": args.profile, "topic": args.topic, "action": "execute", "permission_state": permission, "changed_files": changed, "restored_violations": violations, "outcome_results": outcome_results, "result_contract": {"valid": response is not None, "errors": errors}}
        collaborate.write_json(output, record)
        print(json.dumps({"run_id": run_id, "status": status, "harness": "antigravity", "output_path": str(output.relative_to(collaborate.PROJECT_ROOT))}, ensure_ascii=False))
        return 0 if status == "completed" else 3
    except (collaborate.CollaborationError, HarnessProfileError, AntigravityAdapterError) as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
