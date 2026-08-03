#!/usr/bin/env python3
"""Route a collaboration to Claude Code or the read-only Antigravity role."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import collaborate
from doctor_harness import check as check_harness
from harness_profile_support import HarnessProfileError, load_profiles
from harness_routing import ANTIGRAVITY, CLAUDE_CODE, choose_harness
from harness_state import session_harness
from platform_support import session_matches_workspace
from sensitivity import classify_sensitive_text


SCRIPT_ROOT = Path(__file__).resolve().parent
CLAUDE_RUNNER = SCRIPT_ROOT / "collaborate.py"
ANTIGRAVITY_RUNNER = SCRIPT_ROOT / "consult_antigravity.py"
READ_ONLY_ACTIONS = {"consult", "critique", "continue"}


def antigravity_readiness(profile_name: str) -> tuple[bool, str]:
    """Return only a non-secret readiness reason for the P2 read-only role."""
    try:
        profile = load_profiles(collaborate.CONTROL_ROOT).get(profile_name)
        if not profile:
            return False, "profile_missing"
        if profile.get("mode", "plan") != "plan" or profile.get("dangerously_skip_permissions") is True:
            return False, "profile_not_readonly"
        result = check_harness(profile_name)
    except HarnessProfileError:
        return False, "profile_invalid"
    if result.get("ok") is not True:
        return False, "profile_or_trust_not_ready"
    return True, "ready"


def matching_topic_sessions(topic: str, workdir: Path, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in sessions
        if item.get("status") == "active" and item.get("topic") == topic and session_matches_workspace(item, workdir)
    ]


def exact_session(key: str, workdir: Path, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [item for item in sessions if item.get("status") == "active" and item.get("key") == key]
    if len(matches) != 1:
        raise collaborate.CollaborationError(f"No unique active session with key '{key}'.")
    if not session_matches_workspace(matches[0], workdir):
        raise collaborate.CollaborationError("Session belongs to a different platform or workspace; create a new session instead of resuming it.")
    return matches[0]


def choose_route(args: argparse.Namespace, handoff: str, workdir: Path, sessions: list[dict[str, Any]]) -> tuple[str, dict[str, str]]:
    sensitivity = classify_sensitive_text(handoff)
    if sensitivity.state != "safe":
        raise collaborate.CollaborationError("Handoff must be safe before harness routing.")
    requested = None if args.harness == "auto" else args.harness
    if args.provider != "auto":
        if requested == ANTIGRAVITY:
            raise collaborate.CollaborationError("--provider belongs to the Claude Code pool and cannot be combined with --harness antigravity.")
        requested = CLAUDE_CODE
    if args.session_key:
        session = exact_session(args.session_key, workdir, sessions)
        bound = session_harness(session)
        if requested and requested != bound:
            raise collaborate.CollaborationError("--harness conflicts with the explicit session's harness.")
        if bound == ANTIGRAVITY and args.action not in READ_ONLY_ACTIONS:
            raise collaborate.CollaborationError("An Antigravity session is read-only and cannot be resumed for execute or draft work.")
        return bound, {"basis": "explicit_session_key"}
    matches = matching_topic_sessions(args.topic, workdir, sessions)
    ready, readiness = antigravity_readiness(args.antigravity_profile)
    request = args.request or f"{args.topic}\n{handoff}"
    harness, detail = choose_harness(request, args.action, False, matches, ready, requested)
    basis = detail["basis"]
    if basis == "antigravity_not_ready":
        raise collaborate.CollaborationError(f"Antigravity independent-review role is not ready: {readiness}. Use Codex directly or repair the local read-only profile; do not silently route this request to Claude Code.")
    if basis == "ambiguous_cross_harness_session":
        raise collaborate.CollaborationError("Multiple active sessions for this topic belong to different harnesses; pass --session-key.")
    if basis == "antigravity_session_action_ineligible":
        raise collaborate.CollaborationError("The matching Antigravity session is read-only; start a distinct Claude Code topic for draft or execute work.")
    if harness == ANTIGRAVITY and not ready:
        raise collaborate.CollaborationError(f"Antigravity was selected but is not ready: {readiness}.")
    return harness, detail


def append_if(argv: list[str], flag: str, value: str | None) -> None:
    if value is not None:
        argv.extend([flag, value])


def claude_command(args: argparse.Namespace, basis: str) -> list[str]:
    argv = [sys.executable, str(CLAUDE_RUNNER), "--action", args.action, "--provider", args.provider, "--topic", args.topic, "--handoff", args.handoff, "--working-directory", args.working_directory, "--timeout", str(args.timeout), "--return-mode", args.return_mode, "--response-contract", args.response_contract, "--harness-routing-basis", basis]
    append_if(argv, "--session-key", args.session_key)
    append_if(argv, "--expected-response", args.expected_response)
    append_if(argv, "--task-type", args.task_type)
    append_if(argv, "--mode", args.mode)
    append_if(argv, "--expected-outcomes", args.expected_outcomes)
    append_if(argv, "--topic-goal", args.topic_goal)
    append_if(argv, "--stop-rule", args.stop_rule)
    append_if(argv, "--goal-contract", args.goal_contract)
    append_if(argv, "--goal-state", args.goal_state)
    for flag, values in (("--allow-path", args.allow_path), ("--allow-delete", args.allow_delete), ("--allow-binary-path", args.allow_binary_path), ("--allow-command", args.allow_command), ("--validation-command", args.validation_command), ("--validation-argv", args.validation_argv)):
        for value in values:
            argv.extend([flag, value])
    for flag, enabled in (("--fork-session", args.fork_session), ("--ephemeral", args.ephemeral), ("--stream-diagnostics", args.stream_diagnostics)):
        if enabled:
            argv.append(flag)
    return argv


def antigravity_command(args: argparse.Namespace, basis: str) -> list[str]:
    if args.action not in READ_ONLY_ACTIONS:
        raise collaborate.CollaborationError("Antigravity automatic routing is limited to consult, critique, and an existing read-only continuation.")
    if any((args.allow_path, args.allow_delete, args.allow_binary_path, args.allow_command, args.expected_outcomes, args.validation_command, args.validation_argv, args.fork_session, args.goal_contract, args.goal_state)):
        raise collaborate.CollaborationError("Antigravity read-only routing does not accept execute paths, commands, outcomes, or fork-session.")
    if args.response_contract != "standard" or args.expected_response:
        raise collaborate.CollaborationError("Antigravity role routing requires the standard structured response contract.")
    argv = [sys.executable, str(ANTIGRAVITY_RUNNER), "--action", args.action, "--topic", args.topic, "--handoff", args.handoff, "--profile", args.antigravity_profile, "--working-directory", args.working_directory, "--timeout", str(args.timeout), "--routing-basis", basis]
    append_if(argv, "--session-key", args.session_key)
    return argv


def run_child(argv: list[str]) -> int:
    return subprocess.run(argv, cwd=collaborate.PROJECT_ROOT, check=False).returncode


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--action", required=True, choices=("consult", "continue", "draft", "critique", "execute"))
    p.add_argument("--harness", choices=("auto", CLAUDE_CODE, ANTIGRAVITY), default="auto")
    p.add_argument("--antigravity-profile", default="antigravity_readonly")
    p.add_argument("--request", help="Original user request for role routing; never copied into runtime output.")
    p.add_argument("--provider", default="auto")
    p.add_argument("--topic", required=True)
    p.add_argument("--handoff", required=True)
    p.add_argument("--working-directory", default=str(collaborate.PROJECT_ROOT))
    p.add_argument("--session-key")
    p.add_argument("--fork-session", action="store_true")
    p.add_argument("--allow-path", action="append", default=[])
    p.add_argument("--allow-delete", action="append", default=[])
    p.add_argument("--allow-binary-path", action="append", default=[])
    p.add_argument("--allow-command", action="append", default=[])
    p.add_argument("--expected-outcomes")
    p.add_argument("--validation-command", action="append", default=[])
    p.add_argument("--validation-argv", action="append", default=[])
    p.add_argument("--task-type", choices=("code", "document", "research", "creative", "planning", "data", "file_operations", "personal_advice", "current_information"))
    p.add_argument("--mode", choices=("analyze", "draft", "critique", "revise", "execute", "verify"))
    p.add_argument("--timeout", type=int, default=1200)
    p.add_argument("--ephemeral", action="store_true")
    p.add_argument("--return-mode", choices=collaborate.RETURN_MODES, default="compact")
    p.add_argument("--response-contract", choices=collaborate.RESPONSE_CONTRACT_MODES, default="standard")
    p.add_argument("--expected-response")
    p.add_argument("--stream-diagnostics", action="store_true")
    p.add_argument("--topic-goal")
    p.add_argument("--stop-rule")
    p.add_argument("--goal-contract")
    p.add_argument("--goal-state")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.timeout < 1:
            raise collaborate.CollaborationError("--timeout must be positive.")
        workdir = collaborate.safe_workdir(args.working_directory)
        handoff_path = Path(args.handoff).resolve()
        if not handoff_path.is_file() or collaborate.is_sensitive(collaborate.relative(handoff_path)):
            raise collaborate.CollaborationError("Handoff must be a readable, non-sensitive project file.")
        handoff = handoff_path.read_text(encoding="utf-8")
        collaborate.validate_handoff_sensitivity(handoff)
        sessions = [item for item in collaborate.registry()["sessions"] if isinstance(item, dict)]
        harness, detail = choose_route(args, handoff, workdir, sessions)
        argv = antigravity_command(args, detail["basis"]) if harness == ANTIGRAVITY else claude_command(args, detail["basis"])
        return run_child(argv)
    except collaborate.CollaborationError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
