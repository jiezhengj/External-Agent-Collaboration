#!/usr/bin/env python3
"""Run a bounded, persistent external-agent collaboration through Claude Code."""

from __future__ import annotations

import argparse
import hmac
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_code_adapter import ClaudeCodeAdapter, ClaudeCodeAdapterError, ClaudeInvocation
from harness_state import CLAUDE_CODE, RUNTIME_SCHEMA_VERSION, claude_session_record, external_session_id, session_harness, state_feature_enabled
from platform_support import (
    capability_matches_host,
    host_platform,
    macos_keychain_supported,
    macos_keychain_unavailable_message,
    session_matches_workspace,
    supports_posix_shell_fallback,
    workspace_identity,
)
from profile_support import ProfileConfigError, environment_token, load_profiles
from provider_health import classify_failure, default_health, is_available, record_failure, record_success, status as provider_health_status, valid_health
from provider_routing import append_event, choose_provider, valid_metrics
from sensitivity import classify_sensitive_text


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONTROL_ROOT = PROJECT_ROOT / ".ai-collaboration"
TRUST_FILE = CONTROL_ROOT / "trusted-providers.local.json"
SESSIONS_FILE = CONTROL_ROOT / "sessions.json"
METRICS_FILE = CONTROL_ROOT / "provider-metrics.json"
HEALTH_FILE = CONTROL_ROOT / "provider-health.json"
TOPICS_FILE = CONTROL_ROOT / "topics.json"
SENSITIVE_PARTS = {".git", "secrets", "credentials", "private"}
SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519"}
CONTROL_PARTS = {".ai-collaboration", ".git"}
MAX_SNAPSHOT_BYTES = 500 * 1024 * 1024
RETURN_MODES = ("compact", "structured", "file_only", "debug")
RESPONSE_CONTRACT_MODES = ("standard", "none")
COMPACT_RETURN_BYTES = 8 * 1024
STRUCTURED_RETURN_BYTES = 16 * 1024
TOPIC_STATE_MAX_CHARS = 4096
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
)

RESPONSE_CONTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["summary", "changed_files", "commands_run", "validation_results", "risks", "uncertainty"],
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 4096},
        "changed_files": {"type": "array", "maxItems": 40, "items": {"type": "string", "maxLength": 300}},
        "commands_run": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 300}},
        "validation_results": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 600}},
        "risks": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 600}},
        "uncertainty": {"type": "string", "maxLength": 1200},
    },
    "additionalProperties": False,
}
CLAUDE_ADAPTER = ClaudeCodeAdapter()


class CollaborationError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative(path: Path) -> Path:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise CollaborationError(f"Path is outside project root: {path}") from exc


def is_sensitive(rel: Path) -> bool:
    return any(part in SENSITIVE_PARTS or part in SENSITIVE_NAMES or part.startswith(".env") for part in rel.parts)


def is_controlled(rel: Path) -> bool:
    return bool(rel.parts) and rel.parts[0] in CONTROL_PARTS


def validate_handoff_sensitivity(handoff: str) -> None:
    """Enforce a final value-aware egress scan after task classification.

    Classification decides whether a task is worth delegating. This separate
    check protects the concrete handoff that would be sent to the local CLI and
    intentionally reports only categories, never a matched value.
    """
    finding = classify_sensitive_text(handoff)
    if finding.state == "prohibited":
        raise CollaborationError("Handoff contains prohibited sensitive material (" + ", ".join(finding.categories) + ").")
    if finding.state == "requires_redaction":
        raise CollaborationError("Handoff may reference sensitive material and requires redaction before external collaboration.")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CollaborationError(f"Invalid JSON in {path.relative_to(PROJECT_ROOT)}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def profiles() -> dict[str, dict[str, Any]]:
    try:
        return load_profiles(CONTROL_ROOT)
    except ProfileConfigError as exc:
        raise CollaborationError(str(exc)) from exc


def profile_fingerprint(profile: dict[str, Any]) -> str:
    """Fingerprint non-secret profile configuration without persisting its values."""
    safe = {key: value for key, value in profile.items() if key != "auth_token"}
    safe["runtime_platform"] = host_platform()
    environment = safe.get("environment")
    if isinstance(environment, dict):
        safe["environment"] = {
            key: "[REDACTED]" if any(marker in key.upper() for marker in ("TOKEN", "KEY", "SECRET", "PASSWORD")) else value
            for key, value in environment.items()
        }
    encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def trust_registry() -> dict[str, Any]:
    data = load_json(TRUST_FILE, {"schema_version": 1, "providers": {}})
    if not isinstance(data, dict) or not isinstance(data.get("providers"), dict):
        raise CollaborationError("trusted-providers.local.json must contain a providers object.")
    data.setdefault("schema_version", 1)
    return data


def provider_is_trusted(provider: str, profile: dict[str, Any], trust: dict[str, Any]) -> bool:
    record = trust.get("providers", {}).get(provider)
    return (
        isinstance(record, dict)
        and record.get("harness", CLAUDE_CODE) == CLAUDE_CODE
        and record.get("approved") is True
        and isinstance(record.get("profile_fingerprint"), str)
        and hmac.compare_digest(record["profile_fingerprint"], profile_fingerprint(profile))
    )


def trusted_profiles(configured: dict[str, dict[str, Any]], trust: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {provider: profile for provider, profile in configured.items() if provider_is_trusted(provider, profile, trust)}


def profile_problem(profile: dict[str, Any]) -> str | None:
    direct_token = profile.get("auth_token")
    service = profile.get("auth_token_keychain_service")
    if isinstance(direct_token, str) and direct_token:
        pass
    elif isinstance(profile.get("auth_token_env"), str) and profile.get("auth_token_env"):
        if not environment_token(profile):
            return f"missing authentication environment variable: {profile['auth_token_env']}"
    elif isinstance(service, str) and service:
        if not macos_keychain_supported():
            return macos_keychain_unavailable_message()
        try:
            result = subprocess.run(["security", "find-generic-password", "-s", service], capture_output=True, text=True)
        except OSError:
            return "macOS Keychain command is unavailable"
        if result.returncode != 0:
            return f"missing macOS Keychain password item: {service}"
    else:
        missing = [name for name in profile.get("required_environment", []) if not os.environ.get(name)]
        if missing:
            return "missing required environment variables: " + ", ".join(missing)
    if not Path(str(profile.get("config_dir", ""))).is_dir():
        return "CLAUDE_CONFIG_DIR is unavailable"
    return None


def health_registry() -> dict[str, Any]:
    return valid_health(load_json(HEALTH_FILE, default_health()))


def save_health(data: dict[str, Any]) -> None:
    write_json(HEALTH_FILE, data)


def healthy_providers(available: dict[str, dict[str, Any]], health: dict[str, Any], excluded: set[str] | None = None) -> list[str]:
    excluded = excluded or set()
    return [provider for provider in sorted(available) if provider not in excluded and is_available(health, provider)]


def alternate_provider(current: str, available: dict[str, dict[str, Any]], metrics: dict[str, Any], health: dict[str, Any], task_type: str, mode: str) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    candidates = [provider for provider in healthy_providers(available, health, {current}) if profile_problem(available[provider]) is None]
    if not candidates:
        return None
    provider, route = choose_provider(metrics, candidates, task_type, mode)
    route = {**route, "basis": "availability_failover", "failed_provider": current}
    return provider, available[provider], route


def registry() -> dict[str, Any]:
    data = load_json(SESSIONS_FILE, {"schema_version": 1, "sessions": []})
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
        raise CollaborationError("sessions.json must contain a sessions array.")
    return data


def save_registry(data: dict[str, Any]) -> None:
    data["schema_version"] = max(RUNTIME_SCHEMA_VERSION, int(data.get("schema_version", 1)))
    write_json(SESSIONS_FILE, data)


def topics_registry() -> dict[str, Any]:
    data = load_json(TOPICS_FILE, {"schema_version": 1, "topics": []})
    if not isinstance(data, dict) or not isinstance(data.get("topics"), list):
        raise CollaborationError("topics.json must contain a topics array.")
    return data


def register_topic_session(data: dict[str, Any], session: dict[str, Any], parent_key: str | None = None) -> None:
    matches = [
        item for item in data["topics"]
        if isinstance(item, dict) and item.get("topic") == session["topic"]
        and item.get("workspace_identity") == session.get("workspace_identity")
        and item.get("host_platform") == session.get("host_platform")
    ]
    item = matches[0] if len(matches) == 1 else None
    if item is None:
        item = {
            "topic": session["topic"], "working_directory": session["working_directory"],
            "workspace_identity": session.get("workspace_identity"), "host_platform": session.get("host_platform"),
            "created_at": now(), "sessions": [], "artifact_paths": [], "status": "active",
        }
        data["topics"].append(item)
    session_ref = {
        "key": session["key"], "provider": session["provider"], "model_profile": session["model_profile"],
        "harness": session_harness(session), "harness_profile": session.get("harness_profile"),
        "session_id": session["session_id"], "external_session_id": external_session_id(session),
        "parent_key": parent_key, "created_at": session["created_at"],
        "status": session["status"], "host_platform": session.get("host_platform"),
        "workspace_identity": session.get("workspace_identity"),
    }
    item["sessions"] = [reference for reference in item["sessions"] if reference.get("key") != session["key"]]
    item["sessions"].append(session_ref)
    item["status"] = "active"
    item["last_used_at"] = now()


def safe_workdir(value: str) -> Path:
    workdir = Path(value).resolve()
    relative(workdir)
    if not workdir.is_dir():
        raise CollaborationError(f"Working directory does not exist: {workdir}")
    return workdir


def normalize_allow_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise CollaborationError(f"Allow path must be project-relative and contain no '..': {value}")
    if is_sensitive(candidate) or is_controlled(candidate):
        raise CollaborationError(f"Allow path is forbidden: {value}")
    return candidate


def allowed(rel: Path, paths: list[Path]) -> bool:
    return any(rel == candidate or candidate in rel.parents for candidate in paths)


def select_provider(requested: str, topic: str, workdir: Path, sessions: list[dict[str, Any]], available: dict[str, dict[str, Any]], metrics: dict[str, Any], health: dict[str, Any], task_type: str, mode: str) -> tuple[str, dict[str, Any] | None, bool, dict[str, Any]]:
    topic_matches = [
        item for item in sessions
        if item.get("status") == "active" and item.get("topic") == topic
        and session_matches_workspace(item, workdir)
    ]
    foreign = [item for item in topic_matches if session_harness(item) != CLAUDE_CODE]
    matches = [item for item in topic_matches if session_harness(item) == CLAUDE_CODE]
    if foreign and not matches and state_feature_enabled():
        raise CollaborationError("Matching active session belongs to a different harness; select it through its own harness router instead of creating a Claude Code continuation.")
    if requested != "auto":
        matches = [item for item in matches if item.get("provider") == requested]
        if len(matches) > 1:
            raise CollaborationError("Multiple active sessions match topic/provider/workdir; pass --session-key.")
        return requested, matches[0] if matches else None, False, {"basis": "user_specified"}
    if len(matches) == 1:
        provider = str(matches[0]["provider"])
        if is_available(health, provider):
            return provider, matches[0], False, {"basis": "exact_active_session"}
        fallback = alternate_provider(provider, available, metrics, health, task_type, mode)
        if fallback is None:
            raise CollaborationError(f"Active session provider '{provider}' is in availability cooldown and no healthy alternate provider is configured.")
        alternate, _profile, route = fallback
        return alternate, None, True, {**route, "basis": "active_session_availability_failover", "source_session_key": matches[0].get("key")}
    if len(matches) > 1:
        raise CollaborationError("Multiple active sessions match topic/workdir; select a provider or --session-key.")
    candidates = healthy_providers(available, health)
    if not candidates:
        raise CollaborationError("No configured provider is currently outside availability cooldown.")
    chosen, route = choose_provider(metrics, candidates, task_type, mode)
    return chosen, None, True, route


def find_session(key: str, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [item for item in sessions if item.get("key") == key and item.get("status") == "active"]
    if len(matches) != 1:
        raise CollaborationError(f"No unique active session with key '{key}'.")
    if session_harness(matches[0]) != CLAUDE_CODE:
        raise CollaborationError("Session belongs to a different harness and cannot be resumed by Claude Code.")
    return matches[0]


def copy_checkpoint(run_id: str) -> Path:
    total = sum(path.stat().st_size for path in PROJECT_ROOT.rglob("*") if path.is_file() and not path.is_symlink() and not is_controlled(path.relative_to(PROJECT_ROOT)))
    if total > MAX_SNAPSHOT_BYTES:
        raise CollaborationError(f"Project snapshot is {total} bytes; narrow the workspace before execute (limit {MAX_SNAPSHOT_BYTES}).")
    destination = CONTROL_ROOT / "snapshots" / run_id / "before"
    destination.parent.mkdir(parents=True, exist_ok=True)
    ignored = shutil.ignore_patterns(".git", ".ai-collaboration", "__pycache__", ".DS_Store")
    shutil.copytree(PROJECT_ROOT, destination, ignore=ignored, dirs_exist_ok=False)
    return destination


def manifest(root: Path) -> dict[str, str]:
    output: dict[str, str] = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_symlink():
            output[rel.as_posix()] = "symlink:" + os.readlink(path)
            continue
        if not path.is_file():
            continue
        if is_controlled(rel):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        output[rel.as_posix()] = digest
    return output


def restore_path(rel: Path, checkpoint: Path) -> None:
    target = PROJECT_ROOT / rel
    backup = checkpoint / rel
    if target.exists() or target.is_symlink():
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    if backup.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        if backup.is_dir():
            shutil.copytree(backup, target)
        else:
            shutil.copy2(backup, target)


def restore_changed(before: dict[str, str], after: dict[str, str], checkpoint: Path, only: set[str] | None = None) -> None:
    changed = {path for path in set(before) | set(after) if before.get(path) != after.get(path)}
    for name in sorted(changed if only is None else changed & only, key=lambda item: item.count("/"), reverse=True):
        restore_path(Path(name), checkpoint)


def output_path(run_id: str, suffix: str) -> Path:
    return CONTROL_ROOT / suffix / f"{run_id}.json"


def response_contract_instruction(return_mode: str, response_contract: str) -> str:
    if response_contract == "none":
        return "No JSON response contract is active for this controlled exact-response check. Follow the handoff's required response exactly; do not add explanation, Markdown, or a JSON envelope."
    if return_mode == "debug":
        return "The caller is in explicit debug mode and retains the outer CLI envelope, but your response must still satisfy this schema: " + response_contract_instruction("compact", "standard")
    return """Return exactly one JSON object and no Markdown fence. Its required keys are:
summary (string, at most 4096 characters), changed_files (array of at most 40 short paths),
commands_run (array of at most 20 short commands), validation_results (array of at most 20 short results),
risks (array of at most 20 short items), and uncertainty (short string). Do not include any other keys.
This response contract is separate from machine expected outcomes; never claim an outcome passed unless you ran it."""


def build_prompt(action: str, topic: str, handoff: str, allow_paths: list[Path], commands: list[str], return_mode: str, response_contract: str = "standard") -> str:
    operation = "You may edit files only in the allowed paths." if action == "execute" else "Do not edit files; return your work in the final response."
    return f"""You are a persistent external collaborator for the topic: {topic}.
Action: {action}.
{operation}
Allowed project-relative paths: {', '.join(path.as_posix() for path in allow_paths) or '(none)'}.
Allowed shell command patterns: {', '.join(commands) or '(none)'}.
Never read secrets, commit, push, deploy, publish, rewrite Git history, install global packages, or invoke another agent.
Complete only this handoff. Report files changed, commands run, validation results, remaining risks, and uncertainty.

Response contract:
{response_contract_instruction(return_mode, response_contract)}

Handoff:
{handoff}
"""


def initial_toolset(action: str, commands: list[str]) -> list[str]:
    return CLAUDE_ADAPTER.capabilities(action, commands)


def invoke(profile: dict[str, Any], action: str, prompt: str, workdir: Path, session: dict[str, Any] | None, ephemeral: bool, fork_session: bool, commands: list[str], timeout: int, stream_diagnostics: bool = False, response_contract: str = "standard") -> tuple[int, str, str]:
    launcher = str(profile.get("launcher", "claude"))
    tools = initial_toolset(action, commands)
    allowed_tools = tools.copy()
    if action == "execute":
        if commands:
            allowed_tools.extend(f"Bash({item})" for item in commands)
    return CLAUDE_ADAPTER.invoke(ClaudeInvocation(
        launcher=launcher, prompt=prompt, workdir=workdir, config_dir=str(profile["config_dir"]),
        environment=provider_environment(profile), tools=tools, allowed_tools=allowed_tools, disallowed_tools=[], timeout=timeout,
        session_id=CLAUDE_ADAPTER.resume_id(session) if session and not ephemeral else None,
        ephemeral=ephemeral, fork_session=fork_session,
        response_schema=RESPONSE_CONTRACT_SCHEMA if response_contract == "standard" else None,
        stream_diagnostics=stream_diagnostics,
    ))


def provider_environment(profile: dict[str, Any]) -> dict[str, str]:
    environment = os.environ.copy()
    configured = profile.get("environment", {})
    if not isinstance(configured, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in configured.items()):
        raise CollaborationError("Provider environment must map variable names to non-secret string values.")
    if "ANTHROPIC_AUTH_TOKEN" in configured:
        raise CollaborationError("Store the token only in profile.auth_token, not environment.")
    environment.update(configured)
    direct_token = profile.get("auth_token")
    service = profile.get("auth_token_keychain_service")
    if isinstance(direct_token, str) and direct_token:
        environment["ANTHROPIC_AUTH_TOKEN"] = direct_token
    elif isinstance(profile.get("auth_token_env"), str) and profile.get("auth_token_env"):
        token = environment_token(profile)
        if not token:
            raise CollaborationError(f"Missing authentication environment variable: {profile['auth_token_env']}")
        environment["ANTHROPIC_AUTH_TOKEN"] = token
    elif isinstance(service, str) and service:
        if not macos_keychain_supported():
            raise CollaborationError(macos_keychain_unavailable_message())
        try:
            result = subprocess.run(["security", "find-generic-password", "-s", service, "-w"], capture_output=True, text=True)
        except OSError as exc:
            raise CollaborationError("macOS Keychain command is unavailable") from exc
        if result.returncode != 0:
            raise CollaborationError(f"Missing macOS Keychain password item: {service}")
        token = result.stdout.rstrip("\r\n")
        if not token:
            raise CollaborationError(f"macOS Keychain item is empty: {service}")
        environment["ANTHROPIC_AUTH_TOKEN"] = token
    return environment


def parse_result(stdout: str, stream_diagnostics: bool = False) -> dict[str, Any]:
    try:
        if stream_diagnostics:
            return CLAUDE_ADAPTER.parse_stream_result(stdout)[0]
        return CLAUDE_ADAPTER.parse_outer_result(stdout)
    except ClaudeCodeAdapterError as exc:
        raise CollaborationError(str(exc)) from exc


def outcome_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise CollaborationError(f"Outcome path must be project-relative and contain no '..': {value}")
    if is_sensitive(candidate):
        raise CollaborationError(f"Outcome path is sensitive: {value}")
    return PROJECT_ROOT / candidate


def load_outcomes(path: Path) -> list[dict[str, Any]]:
    rel = relative(path)
    if is_sensitive(rel) or not path.is_file():
        raise CollaborationError("Expected outcomes must be a readable, non-sensitive project JSON file.")
    data = load_json(path, None)
    if not isinstance(data, dict) or not isinstance(data.get("outcomes"), list) or not data["outcomes"]:
        raise CollaborationError("Expected outcomes JSON must contain a non-empty outcomes array.")
    if not all(isinstance(item, dict) and isinstance(item.get("type"), str) for item in data["outcomes"]):
        raise CollaborationError("Each expected outcome must be an object with a string type.")
    return data["outcomes"]


def required_new_files(outcomes: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    for item in outcomes:
        if item.get("type") in {"file_exists", "file_contains", "file_equals", "json_schema"} and isinstance(item.get("path"), str):
            path = outcome_path(item["path"])
            if not path.exists() and path not in paths:
                paths.append(path)
    return paths


def ensure_creation_capability(provider: str) -> dict[str, Any]:
    probe = Path(__file__).with_name("probe_capabilities.py")
    completed = subprocess.run([sys.executable, str(probe), "--provider", provider], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600)
    if completed.returncode != 0:
        raise CollaborationError(f"Capability probe failed for {provider}: {completed.stderr[-800:] or completed.stdout[-800:]}")
    records = load_json(CONTROL_ROOT / "provider-capabilities.json", {"providers": {}})
    record = records.get("providers", {}).get(provider) if isinstance(records, dict) else None
    if not isinstance(record, dict):
        raise CollaborationError(f"Capability probe produced no record for {provider}.")
    if not capability_matches_host(record):
        raise CollaborationError(f"Capability probe produced a record for a different host platform: {provider}.")
    return record


def bash_create_commands(paths: list[Path]) -> list[str]:
    if not supports_posix_shell_fallback():
        raise CollaborationError("Bash creation fallback is unavailable on this host; fork or create a session with native Write.")
    commands: list[str] = []
    for path in paths:
        parent = path.parent.relative_to(PROJECT_ROOT)
        rel = path.relative_to(PROJECT_ROOT)
        command = f"mkdir -p {shlex.quote(str(parent))} && touch {shlex.quote(str(rel))}"
        if command not in commands:
            commands.append(command)
    return commands


def binary_changed_paths(paths: list[str]) -> list[str]:
    unsafe: list[str] = []
    for name in paths:
        candidate = PROJECT_ROOT / name
        if candidate.is_file() and not candidate.is_symlink() and b"\0" in candidate.read_bytes()[:8192]:
            unsafe.append(name)
    return unsafe


def schema_errors(value: Any, schema: dict[str, Any], location: str = "$") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    types = expected_type if isinstance(expected_type, list) else [expected_type]
    type_match = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if expected_type is not None and not any(name in type_match and type_match[name](value) for name in types):
        return [f"{location}: expected type {expected_type}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: expected const {schema['const']!r}")
    if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
        errors.append(f"{location}: value is not in enum")
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            errors.append(f"{location}: shorter than minLength")
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            errors.append(f"{location}: longer than maxLength")
        if isinstance(schema.get("pattern"), str) and re.search(schema["pattern"], value) is None:
            errors.append(f"{location}: does not match pattern")
    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            errors.append(f"{location}: fewer than minItems")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            errors.append(f"{location}: more than maxItems")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema["items"], f"{location}[{index}]"))
    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append(f"{location}: missing required property {key}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child in properties.items():
                if key in value and isinstance(child, dict):
                    errors.extend(schema_errors(value[key], child, f"{location}.{key}"))
            if schema.get("additionalProperties") is False:
                extras = set(value) - set(properties)
                if extras:
                    errors.append(f"{location}: unexpected properties {sorted(extras)}")
    return errors


def truncate_utf8(value: str, limit: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value, False
    clipped = encoded[:limit]
    while clipped:
        try:
            return clipped.decode("utf-8") + "…", True
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return "…", True


def redact_return_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def redact_return_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_return_text(value)
    if isinstance(value, list):
        return [redact_return_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_return_value(item) for key, item in value.items()}
    return value


def one_line(value: str, limit: int) -> str:
    compact = " ".join(redact_return_text(value).split())
    return truncate_utf8(compact, limit)[0]


def result_text(result: dict[str, Any]) -> str:
    value = result.get("result")
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def has_permission_denial(result: dict[str, Any]) -> bool:
    """`dontAsk` must surface a denied action as a blocked run, never silent success."""
    return bool(result.get("permission_denials"))


def parse_response_contract(result: dict[str, Any], response_contract: str = "standard") -> tuple[dict[str, Any] | None, list[str]]:
    if response_contract == "none":
        return None, []
    try:
        value, source = CLAUDE_ADAPTER.structured_output(result)
    except ClaudeCodeAdapterError as exc:
        return None, [str(exc)]
    if source is None:
        raw = result.get("result")
        if not isinstance(raw, str):
            return None, ["result is not a JSON string and structured_output is absent"]
        candidate = raw.strip()
        if candidate.startswith("```json") and candidate.endswith("```"):
            candidate = candidate[7:-3].strip()
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as exc:
            return None, [f"result is not valid JSON: {exc.msg}"]
    errors = schema_errors(value, RESPONSE_CONTRACT_SCHEMA)
    if errors:
        return None, errors[:12]
    return value, []


def exact_response_errors(result: dict[str, Any], expected: str | None) -> list[str]:
    """Validate explicit smoke text without conflating it with the JSON contract."""
    if expected is None:
        return []
    raw = result.get("result")
    if not isinstance(raw, str):
        return ["result is not a text response for --expected-response"]
    if raw.strip() != expected:
        return ["result did not match --expected-response exactly"]
    return []


def compact_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in outcomes[:20]:
        record = {key: item[key] for key in ("type", "path", "command", "argv", "passed", "count") if key in item}
        if isinstance(item.get("error"), str):
            record["error"] = one_line(item["error"], 240)
        compact.append(record)
    return compact


def bounded_payload(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= limit:
        return payload
    fallback = {
        "run_id": payload.get("run_id"), "status": payload.get("status"), "provider": payload.get("provider"),
        "action": payload.get("action"), "topic": payload.get("topic"), "output_path": payload.get("output_path"),
        "truncated": True, "message": "Return envelope exceeded its budget; inspect the local output path by explicit request.",
    }
    return fallback


def return_payload(return_mode: str, record: dict[str, Any], output_rel: str, response: dict[str, Any] | None, contract_errors: list[str]) -> dict[str, Any]:
    common = {
        "run_id": record["run_id"], "status": record["status"], "provider": record["provider"],
        "action": record["action"], "task_type": record["task_type"], "mode": record["mode"],
        "topic": record["topic"], "routing": record["routing"], "provider_health": record.get("provider_health"), "output_path": output_rel,
        "result_contract_failed": bool(contract_errors), "response_acceptance_failed": bool(record.get("response_acceptance_errors")),
    }
    if return_mode == "debug":
        return record
    if return_mode == "file_only":
        payload = {**common, "output_sha256": hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()}
        return bounded_payload(payload, COMPACT_RETURN_BYTES)
    if return_mode == "structured" and response is not None:
        return bounded_payload({**common, "response": redact_return_value(response), "changed_files": record["changed_files"], "outcome_results": compact_outcomes(record["outcome_results"])}, STRUCTURED_RETURN_BYTES)
    summary, truncated = truncate_utf8(redact_return_text(result_text(record["result"])), 3072)
    payload = {
        **common, "result_summary": summary, "result_truncated": truncated,
        "changed_files": record["changed_files"][:40], "changed_file_count": len(record["changed_files"]),
        "restored_violations": record["restored_violations"][:20],
        "outcome_results": compact_outcomes(record["outcome_results"]),
    }
    if contract_errors:
        payload["result_contract_errors"] = [one_line(item, 240) for item in contract_errors[:12]]
    if record.get("response_acceptance_errors"):
        payload["response_acceptance_errors"] = [one_line(str(item), 240) for item in record["response_acceptance_errors"][:12]]
    return bounded_payload(payload, COMPACT_RETURN_BYTES)


def topic_filename(topic: str) -> str:
    slug = re.sub(r"[^\w.-]+", "-", topic, flags=re.UNICODE).strip(".-")[:72] or "topic"
    digest = hashlib.sha256(topic.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}.md"


def write_topic_state(topic: str, workdir: Path, goal: str | None, stop_rule: str | None, status: str, action: str, changed: list[str], output_rel: str) -> str:
    path = CONTROL_ROOT / "topics" / topic_filename(topic)
    scope = ", ".join(f"`{name}`" for name in changed[:12]) or "No project files changed in this run."
    text = f"""# Topic: {topic}

- Goal: {one_line(goal or 'Continue the scoped work for this topic.', 600)}
- Scope: {scope}
- Decisions: Read `decisions.md` only when a confirmed decision is needed.
- State: {status} after `{action}`.
- Next: Inspect the recorded outcomes and continue only if the stop rule is not met.
- Evidence: `{output_rel}`
- Stop rule: {one_line(stop_rule or 'Complete the machine outcomes and resolve recorded exceptions.', 600)}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(truncate_utf8(text, TOPIC_STATE_MAX_CHARS)[0] + "\n", encoding="utf-8")
    return str(path.relative_to(PROJECT_ROOT))


def evaluate_outcomes(outcomes: list[dict[str, Any]], changed: list[str], workdir: Path, validation_commands: list[str], validation_argvs: list[list[str]] | None = None) -> list[dict[str, Any]]:
    validation_argvs = validation_argvs or []
    results: list[dict[str, Any]] = []
    for item in outcomes:
        kind = item["type"]
        result: dict[str, Any] = {"type": kind, "passed": False}
        try:
            if kind == "file_exists":
                path = outcome_path(str(item["path"]))
                result.update({"path": str(path.relative_to(PROJECT_ROOT)), "passed": path.is_file()})
            elif kind == "file_contains":
                path = outcome_path(str(item["path"]))
                text = item.get("text")
                if not isinstance(text, str):
                    raise CollaborationError("file_contains requires a string text.")
                result.update({"path": str(path.relative_to(PROJECT_ROOT)), "passed": path.is_file() and text in path.read_text(encoding="utf-8")})
            elif kind == "file_equals":
                path = outcome_path(str(item["path"]))
                text = item.get("text")
                if not isinstance(text, str):
                    raise CollaborationError("file_equals requires a string text.")
                result.update({"path": str(path.relative_to(PROJECT_ROOT)), "passed": path.is_file() and path.read_text(encoding="utf-8") == text})
            elif kind == "json_schema":
                path = outcome_path(str(item["path"]))
                schema = item.get("schema")
                if not isinstance(schema, dict) or not path.is_file():
                    result.update({"path": str(path.relative_to(PROJECT_ROOT)), "error": "missing JSON file or schema"})
                else:
                    value = json.loads(path.read_text(encoding="utf-8"))
                    errors = schema_errors(value, schema)
                    result.update({"path": str(path.relative_to(PROJECT_ROOT)), "errors": errors, "passed": not errors})
            elif kind == "changed_paths":
                minimum = item.get("min", 0)
                maximum = item.get("max")
                if not isinstance(minimum, int) or (maximum is not None and not isinstance(maximum, int)):
                    raise CollaborationError("changed_paths min/max must be integers.")
                passed = len(changed) >= minimum and (maximum is None or len(changed) <= maximum)
                result.update({"count": len(changed), "passed": passed})
            elif kind == "command_succeeds":
                argv = item.get("argv")
                if isinstance(argv, list):
                    if not argv or not all(isinstance(value, str) and value for value in argv) or argv not in validation_argvs:
                        raise CollaborationError("command_succeeds argv must exactly match one --validation-argv JSON array.")
                    completed = subprocess.run(argv, cwd=workdir, shell=False, capture_output=True, text=True, timeout=180)
                    result.update({"argv": argv, "exit_code": completed.returncode, "passed": completed.returncode == 0, "stderr": completed.stderr[-2000:]})
                else:
                    command = item.get("command")
                    if not isinstance(command, str) or command not in validation_commands:
                        raise CollaborationError("command_succeeds must exactly match one --validation-command or --validation-argv.")
                    completed = subprocess.run(command, cwd=workdir, shell=True, capture_output=True, text=True, timeout=180)
                    result.update({"command": command, "exit_code": completed.returncode, "passed": completed.returncode == 0, "stderr": completed.stderr[-2000:]})
            else:
                raise CollaborationError(f"Unsupported expected outcome type: {kind}")
        except (CollaborationError, OSError, UnicodeDecodeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            result["error"] = str(exc)
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=("consult", "continue", "draft", "critique", "execute"))
    parser.add_argument("--provider", default="auto")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--working-directory", default=str(PROJECT_ROOT))
    parser.add_argument("--session-key")
    parser.add_argument("--fork-session", action="store_true")
    parser.add_argument("--skip-capability-check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--allow-path", action="append", default=[])
    parser.add_argument("--allow-delete", action="append", default=[])
    parser.add_argument("--allow-binary-path", action="append", default=[])
    parser.add_argument("--allow-command", action="append", default=[])
    parser.add_argument("--expected-outcomes")
    parser.add_argument("--validation-command", action="append", default=[])
    parser.add_argument("--validation-argv", action="append", default=[], help="JSON array for a shell-free validation command.")
    parser.add_argument("--task-type", choices=("code", "document", "research", "creative", "planning", "data", "file_operations", "personal_advice", "current_information"))
    parser.add_argument("--mode", choices=("analyze", "draft", "critique", "revise", "execute", "verify"))
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--ephemeral", action="store_true")
    parser.add_argument("--return-mode", choices=RETURN_MODES, default="compact", help="stdout shape; full CLI JSON always remains in local outputs.")
    parser.add_argument("--response-contract", choices=RESPONSE_CONTRACT_MODES, default="standard", help="Use none only for a bounded read-only exact-response smoke check.")
    parser.add_argument("--expected-response", help="Exact trimmed text required when --response-contract none is used for a smoke check.")
    parser.add_argument("--stream-diagnostics", action="store_true", help="Opt in to content-free stream-json lifecycle diagnostics; final result handling remains structured.")
    parser.add_argument("--topic-goal", help="Short durable goal for the one-page topic state; never include secrets or a full handoff.")
    parser.add_argument("--stop-rule", help="Short durable stop rule for the one-page topic state.")
    args = parser.parse_args()
    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    started_monotonic = time.monotonic()
    action_modes = {"consult": "analyze", "continue": "analyze", "draft": "draft", "critique": "critique", "execute": "execute"}
    task_type = args.task_type or "planning"
    mode = args.mode or action_modes[args.action]
    log: dict[str, Any] = {"run_id": run_id, "started_at": now(), "action": args.action, "topic": args.topic, "task_type": task_type, "mode": mode, "return_mode": args.return_mode, "response_contract": args.response_contract, "harness_state_feature": state_feature_enabled()}
    try:
        if args.timeout < 1:
            raise CollaborationError("--timeout must be positive.")
        if args.response_contract == "none":
            if args.action not in {"consult", "critique"} or not args.ephemeral:
                raise CollaborationError("--response-contract none is limited to an ephemeral consult or critique smoke check.")
            if args.return_mode == "structured":
                raise CollaborationError("--response-contract none cannot use --return-mode structured.")
            if not isinstance(args.expected_response, str) or not args.expected_response or "\n" in args.expected_response:
                raise CollaborationError("--response-contract none requires a non-empty single-line --expected-response.")
        elif args.expected_response is not None:
            raise CollaborationError("--expected-response requires --response-contract none.")
        workdir = safe_workdir(args.working_directory)
        handoff_file = Path(args.handoff).resolve()
        handoff_rel = relative(handoff_file)
        if is_sensitive(handoff_rel) or not handoff_file.is_file():
            raise CollaborationError("Handoff must be a readable, non-sensitive project file.")
        handoff = handoff_file.read_text(encoding="utf-8")
        validate_handoff_sensitivity(handoff)
        allow_paths = [normalize_allow_path(value) for value in args.allow_path]
        if args.action == "execute" and not allow_paths:
            raise CollaborationError("execute requires at least one --allow-path.")
        if args.action == "execute" and not args.expected_outcomes:
            raise CollaborationError("execute requires --expected-outcomes.")
        delete_paths = [normalize_allow_path(value) for value in args.allow_delete]
        binary_paths = [normalize_allow_path(value) for value in args.allow_binary_path]
        if any(not allowed(path, allow_paths) for path in delete_paths + binary_paths):
            raise CollaborationError("Delete/binary paths must be inside an --allow-path.")
        if args.action != "execute" and (allow_paths or delete_paths or binary_paths or args.allow_command or args.expected_outcomes or args.validation_command or args.validation_argv):
            raise CollaborationError("Execution paths, commands, and outcomes are only valid for execute.")
        if any("\n" in command or command.strip() in {"", "*"} for command in args.allow_command):
            raise CollaborationError("Each allowed command must be a non-empty single-line pattern.")
        if any("\n" in command or command.strip() == "" for command in args.validation_command):
            raise CollaborationError("Each validation command must be a non-empty single line.")
        validation_argvs: list[list[str]] = []
        for value in args.validation_argv:
            try:
                argv = json.loads(value)
            except json.JSONDecodeError as exc:
                raise CollaborationError(f"--validation-argv must be a JSON array: {exc.msg}") from exc
            if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
                raise CollaborationError("Each --validation-argv must be a non-empty JSON string array.")
            validation_argvs.append(argv)
        outcomes = load_outcomes(Path(args.expected_outcomes).resolve()) if args.action == "execute" else []
        new_files = required_new_files(outcomes) if args.action == "execute" else []
        configured = profiles()
        trust = trust_registry()
        available = trusted_profiles(configured, trust)
        if args.provider != "auto" and args.provider not in available:
            raise CollaborationError(f"Provider '{args.provider}' is not approved for external collaboration, or its non-secret profile configuration changed. Run trust_provider.py --provider {args.provider} --approve after user approval.")
        if args.provider == "auto" and not available:
            raise CollaborationError("No configured provider has a current user-approved trust record. Run trust_provider.py --provider <key> --approve after user approval.")
        data = registry()
        metrics = valid_metrics(load_json(METRICS_FILE, {"schema_version": 1, "round_robin_cursor": {}, "events": []}))
        health = health_registry()
        sessions = [item for item in data["sessions"] if isinstance(item, dict)]
        if args.session_key:
            session = find_session(args.session_key, sessions)
            provider = str(session["provider"])
            if args.provider != "auto" and args.provider != provider:
                raise CollaborationError("--provider conflicts with --session-key.")
            if not session_matches_workspace(session, workdir):
                raise CollaborationError("Session belongs to a different platform or workspace; create a new session instead of resuming it.")
            auto_selected = False
            route = {"basis": "explicit_session_key"}
        else:
            provider, session, auto_selected, route = select_provider(args.provider, args.topic, workdir, sessions, available, metrics, health, task_type, mode)
        if args.fork_session and (session is None or args.ephemeral):
            raise CollaborationError("--fork-session requires a resolved persistent active session and cannot be ephemeral.")
        profile = available.get(provider)
        if not profile:
            raise CollaborationError(f"Provider '{provider}' has no configured profile.")
        problem = profile_problem(profile)
        if problem:
            if args.provider == "auto":
                record_failure(health, provider, "configuration")
                save_health(health)
            fallback = alternate_provider(provider, available, metrics, health, task_type, mode) if args.provider == "auto" else None
            if fallback is None:
                raise CollaborationError(f"Provider profile is not ready: {problem}")
            failed_provider = provider
            provider, profile, route = fallback
            session = None
            log["profile_failover"] = {"from": failed_provider, "to": provider, "failure_kind": "configuration"}
        log.update({"provider": provider, "auto_selected": auto_selected, "session_key": session.get("key") if session else None, "routing": route, "provider_health_before": provider_health_status(health, provider)})

        effective_fork = args.fork_session
        commands = list(args.allow_command)
        if new_files and not args.skip_capability_check:
            capability = ensure_creation_capability(provider)
            log["creation_capability"] = {"native_write": capability.get("native_write"), "bash_create_fallback": capability.get("bash_create_fallback")}
            existing_tools = set(session.get("initial_toolset", [])) if session else set(initial_toolset(args.action, commands))
            if "Write" not in existing_tools:
                if capability.get("native_write") and session and not args.ephemeral:
                    effective_fork = True
                    log["automatic_fork_reason"] = "resumed_session_lacks_Write"
                elif capability.get("bash_create_fallback") and capability.get("shell_kind") == "posix":
                    commands.extend(command for command in bash_create_commands(new_files) if command not in commands)
                    log["creation_fallback"] = "exact_bash_create"
                else:
                    raise CollaborationError("Provider cannot create required output files with the verified toolset.")

        checkpoint: Path | None = None
        before: dict[str, str] = {}
        if args.action == "execute":
            checkpoint = copy_checkpoint(run_id)
            before = manifest(PROJECT_ROOT)
        prompt = build_prompt(args.action, args.topic, handoff, allow_paths, commands, args.return_mode, args.response_contract)
        exit_code, stdout, stderr = invoke(profile, args.action, prompt, workdir, session, args.ephemeral, effective_fork, commands, args.timeout, args.stream_diagnostics, args.response_contract)
        log.update({"exit_code": exit_code, "stderr": one_line(stderr, 1200)})

        if exit_code != 0:
            failure_kind = classify_failure(exit_code, stderr)
            if failure_kind:
                record_failure(health, provider, failure_kind)
                save_health(health)
            fallback = alternate_provider(provider, available, metrics, health, task_type, mode) if args.provider == "auto" and failure_kind else None
            if fallback is None:
                if checkpoint:
                    restore_changed(before, manifest(PROJECT_ROOT), checkpoint)
                reason = f"availability failure ({failure_kind})" if failure_kind else "non-availability failure; no provider failover"
                raise CollaborationError(f"Claude CLI failed with exit code {exit_code}: {reason}: {one_line(stderr, 800)}")
            if checkpoint:
                restore_changed(before, manifest(PROJECT_ROOT), checkpoint)
            failed_provider = provider
            provider, profile, route = fallback
            session = None
            exit_code, stdout, stderr = invoke(profile, args.action, prompt, workdir, None, args.ephemeral, False, commands, args.timeout, args.stream_diagnostics, args.response_contract)
            log.update({"provider_failover": {"from": failed_provider, "to": provider, "failure_kind": failure_kind}, "exit_code": exit_code, "stderr": one_line(stderr, 1200)})
            if exit_code != 0:
                fallback_kind = classify_failure(exit_code, stderr)
                if fallback_kind:
                    record_failure(health, provider, fallback_kind)
                    save_health(health)
                if checkpoint:
                    restore_changed(before, manifest(PROJECT_ROOT), checkpoint)
                raise CollaborationError(f"Fallback Claude CLI failed with exit code {exit_code}: {one_line(stderr, 800)}")
        record_success(health, provider)
        save_health(health)
        result = parse_result(stdout, args.stream_diagnostics)
        stream_summary: dict[str, Any] | None = None
        if args.stream_diagnostics:
            try:
                _terminal, stream_summary = CLAUDE_ADAPTER.parse_stream_result(stdout)
            except ClaudeCodeAdapterError as exc:
                raise CollaborationError(str(exc)) from exc
        permission_denied = has_permission_denial(result)
        response, contract_errors = parse_response_contract(result, args.response_contract)
        exact_errors = exact_response_errors(result, args.expected_response)
        changed: list[str] = []
        violations: list[str] = []
        outcome_results: list[dict[str, Any]] = []
        if checkpoint:
            after = manifest(PROJECT_ROOT)
            changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
            deleted = [path for path in changed if path in before and path not in after]
            binary = binary_changed_paths(changed)
            violations = [path for path in changed if is_sensitive(Path(path)) or not allowed(Path(path), allow_paths)]
            violations.extend(path for path in deleted if not allowed(Path(path), delete_paths))
            violations.extend(path for path in binary if not allowed(Path(path), binary_paths))
            outcome_results = evaluate_outcomes(outcomes, changed, workdir, args.validation_command, validation_argvs)
            after_validation = manifest(PROJECT_ROOT)
            changed = sorted(path for path in set(before) | set(after_validation) if before.get(path) != after_validation.get(path))
            deleted = [path for path in changed if path in before and path not in after_validation]
            binary = binary_changed_paths(changed)
            violations = [path for path in changed if is_sensitive(Path(path)) or not allowed(Path(path), allow_paths)]
            violations.extend(path for path in deleted if not allowed(Path(path), delete_paths))
            violations.extend(path for path in binary if not allowed(Path(path), binary_paths))
            violations = sorted(set(violations))
        outcome_failures = [item for item in outcome_results if not item.get("passed")]
        if permission_denied:
            if checkpoint:
                restore_changed(before, manifest(PROJECT_ROOT), checkpoint)
            status = "blocked_by_permission"
        elif outcome_failures or exact_errors:
            if checkpoint:
                restore_changed(before, manifest(PROJECT_ROOT), checkpoint)
            status = "failed"
        elif violations:
            if checkpoint:
                restore_changed(before, manifest(PROJECT_ROOT), checkpoint, set(violations))
            status = "needs_review"
        else:
            status = "completed"
        log.update({"status": status, "permission_denied": permission_denied, "changed_files": changed, "deleted_files": deleted if checkpoint else [], "binary_files": binary if checkpoint else [], "restored_violations": violations, "outcome_results": outcome_results, "provider_health_after": provider_health_status(health, provider)})
        if stream_summary is not None:
            log["stream_diagnostics"] = stream_summary
        duration_seconds = round(time.monotonic() - started_monotonic, 3)
        append_event(metrics, {
            "run_id": run_id, "timestamp": now(), "provider": provider, "model_profile": provider,
            "harness": CLAUDE_CODE, "harness_profile": provider,
            "task_type": task_type, "mode": mode, "status": status, "duration_seconds": duration_seconds,
            "tool_refusal": bool(result.get("permission_denials")) or (exit_code == 0 and "not available" in str(result).lower()),
            "cost_usd": result.get("total_cost_usd") if isinstance(result.get("total_cost_usd"), (int, float)) else None,
            "rework_count": 0, "route_basis": route.get("basis"),
        })
        write_json(METRICS_FILE, metrics)
        output_file = output_path(run_id, "outputs")
        output_rel = str(output_file.relative_to(PROJECT_ROOT))
        result_record = {"run_id": run_id, "status": status, "provider": provider, "action": args.action, "task_type": task_type, "mode": mode, "routing": route, "topic": args.topic, "result": result, "permission_denied": permission_denied, "changed_files": changed, "restored_violations": violations, "outcome_results": outcome_results, "return_mode": args.return_mode, "provider_health": provider_health_status(health, provider), "result_contract": {"mode": args.response_contract, "valid": args.response_contract == "none" or response is not None, "errors": contract_errors}, "response_acceptance_errors": exact_errors}
        if stream_summary is not None:
            result_record["stream_diagnostics"] = stream_summary
        write_json(output_file, result_record)
        if not args.ephemeral and isinstance(result.get("session_id"), str):
            parent_key = session.get("key") if effective_fork and session else None
            if session is None or effective_fork:
                session = {
                    "key": f"{args.topic}-{provider}-{uuid.uuid4().hex[:6]}", "topic": args.topic,
                    "provider": provider, "model_profile": provider, "working_directory": str(workdir),
                    "workspace_identity": workspace_identity(workdir), "host_platform": host_platform(),
                    "session_id": result["session_id"], "initial_toolset": initial_toolset(args.action, commands),
                    "status": "active", "parent_key": parent_key, "created_at": now(),
                    **claude_session_record(provider, host_platform(), result["session_id"]),
                }
                data["sessions"].append(session)
            session["last_used_at"] = now()
            save_registry(data)
            topic_data = topics_registry()
            register_topic_session(topic_data, session, parent_key)
            write_json(TOPICS_FILE, topic_data)
        if not args.ephemeral:
            result_record["topic_state_path"] = write_topic_state(args.topic, workdir, args.topic_goal, args.stop_rule, status, args.action, changed, output_rel)
            write_json(output_file, result_record)
        log["finished_at"] = now()
        log["result_contract"] = result_record["result_contract"]
        write_json(output_path(run_id, "logs"), log)
        print(json.dumps(return_payload(args.return_mode, result_record, output_rel, response, contract_errors), ensure_ascii=False, indent=2))
        return 0 if status == "completed" else 3
    except CollaborationError as exc:
        log.update({"status": "failed", "error": str(exc), "finished_at": now()})
        write_json(output_path(run_id, "logs"), log)
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
