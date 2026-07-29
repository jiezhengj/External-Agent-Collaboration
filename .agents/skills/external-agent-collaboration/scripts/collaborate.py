#!/usr/bin/env python3
"""Run a bounded, persistent external-agent collaboration through Claude Code."""

from __future__ import annotations

import argparse
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

from provider_routing import append_event, choose_provider, valid_metrics


PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONTROL_ROOT = PROJECT_ROOT / ".ai-collaboration"
PROFILE_FILE = CONTROL_ROOT / "providers.local.json"
SESSIONS_FILE = CONTROL_ROOT / "sessions.json"
METRICS_FILE = CONTROL_ROOT / "provider-metrics.json"
TOPICS_FILE = CONTROL_ROOT / "topics.json"
SENSITIVE_PARTS = {".git", "secrets", "credentials", "private"}
SENSITIVE_NAMES = {".env", "id_rsa", "id_ed25519"}
CONTROL_PARTS = {".ai-collaboration", ".git"}
MAX_SNAPSHOT_BYTES = 500 * 1024 * 1024
RETURN_MODES = ("compact", "structured", "file_only", "debug")
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
    data = load_json(PROFILE_FILE, None)
    if not isinstance(data, dict):
        raise CollaborationError(
            "Provider profiles are missing. Copy .ai-collaboration/providers.local.example.json "
            "to providers.local.json and configure isolated profiles."
        )
    return {key: value for key, value in data.items() if isinstance(value, dict)}


def profile_problem(profile: dict[str, Any]) -> str | None:
    direct_token = profile.get("auth_token")
    service = profile.get("auth_token_keychain_service")
    if isinstance(direct_token, str) and direct_token:
        pass
    elif isinstance(service, str) and service:
        result = subprocess.run(["security", "find-generic-password", "-s", service], capture_output=True, text=True)
        if result.returncode != 0:
            return f"missing macOS Keychain password item: {service}"
    else:
        missing = [name for name in profile.get("required_environment", []) if not os.environ.get(name)]
        if missing:
            return "missing required environment variables: " + ", ".join(missing)
    if not Path(str(profile.get("config_dir", ""))).is_dir():
        return "CLAUDE_CONFIG_DIR is unavailable"
    return None


def alternate_provider(current: str, available: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    for candidate in sorted(available):
        profile = available.get(candidate)
        if candidate != current and profile and profile_problem(profile) is None:
            return candidate, profile
    return None


def registry() -> dict[str, Any]:
    data = load_json(SESSIONS_FILE, {"schema_version": 1, "sessions": []})
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
        raise CollaborationError("sessions.json must contain a sessions array.")
    return data


def save_registry(data: dict[str, Any]) -> None:
    write_json(SESSIONS_FILE, data)


def topics_registry() -> dict[str, Any]:
    data = load_json(TOPICS_FILE, {"schema_version": 1, "topics": []})
    if not isinstance(data, dict) or not isinstance(data.get("topics"), list):
        raise CollaborationError("topics.json must contain a topics array.")
    return data


def register_topic_session(data: dict[str, Any], session: dict[str, Any], parent_key: str | None = None) -> None:
    matches = [item for item in data["topics"] if isinstance(item, dict) and item.get("topic") == session["topic"] and item.get("working_directory") == session["working_directory"]]
    item = matches[0] if len(matches) == 1 else None
    if item is None:
        item = {"topic": session["topic"], "working_directory": session["working_directory"], "created_at": now(), "sessions": [], "artifact_paths": [], "status": "active"}
        data["topics"].append(item)
    session_ref = {"key": session["key"], "provider": session["provider"], "model_profile": session["model_profile"], "session_id": session["session_id"], "parent_key": parent_key, "created_at": session["created_at"], "status": session["status"]}
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


def select_provider(requested: str, topic: str, workdir: Path, sessions: list[dict[str, Any]], available: dict[str, dict[str, Any]], metrics: dict[str, Any], task_type: str, mode: str) -> tuple[str, dict[str, Any] | None, bool, dict[str, Any]]:
    matches = [
        item for item in sessions
        if item.get("status") == "active" and item.get("topic") == topic
        and item.get("working_directory") == str(workdir)
    ]
    if requested != "auto":
        matches = [item for item in matches if item.get("provider") == requested]
        if len(matches) > 1:
            raise CollaborationError("Multiple active sessions match topic/provider/workdir; pass --session-key.")
        return requested, matches[0] if matches else None, False, {"basis": "user_specified"}
    if len(matches) == 1:
        return str(matches[0]["provider"]), matches[0], False, {"basis": "exact_active_session"}
    if len(matches) > 1:
        raise CollaborationError("Multiple active sessions match topic/workdir; select a provider or --session-key.")
    candidates = sorted(available)
    if not candidates:
        raise CollaborationError("No configured provider profiles are available.")
    chosen, route = choose_provider(metrics, candidates, task_type, mode)
    return chosen, None, True, route


def find_session(key: str, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [item for item in sessions if item.get("key") == key and item.get("status") == "active"]
    if len(matches) != 1:
        raise CollaborationError(f"No unique active session with key '{key}'.")
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


def response_contract_instruction(return_mode: str) -> str:
    if return_mode == "debug":
        return "Return a concise final response; the caller is in explicit debug mode."
    return """Return exactly one JSON object and no Markdown fence. Its required keys are:
summary (string, at most 4096 characters), changed_files (array of at most 40 short paths),
commands_run (array of at most 20 short commands), validation_results (array of at most 20 short results),
risks (array of at most 20 short items), and uncertainty (short string). Do not include any other keys.
This response contract is separate from machine expected outcomes; never claim an outcome passed unless you ran it."""


def build_prompt(action: str, topic: str, handoff: str, allow_paths: list[Path], commands: list[str], return_mode: str) -> str:
    operation = "You may edit files only in the allowed paths." if action == "execute" else "Do not edit files; return your work in the final response."
    return f"""You are a persistent external collaborator for the topic: {topic}.
Action: {action}.
{operation}
Allowed project-relative paths: {', '.join(path.as_posix() for path in allow_paths) or '(none)'}.
Allowed shell command patterns: {', '.join(commands) or '(none)'}.
Never read secrets, commit, push, deploy, publish, rewrite Git history, install global packages, or invoke another agent.
Complete only this handoff. Report files changed, commands run, validation results, remaining risks, and uncertainty.

Response contract:
{response_contract_instruction(return_mode)}

Handoff:
{handoff}
"""


def initial_toolset(action: str, commands: list[str]) -> list[str]:
    tools = ["Read", "Glob", "Grep"]
    if action == "execute":
        tools.extend(["Edit", "Write"])
        if commands:
            tools.append("Bash")
    return tools


def invoke(profile: dict[str, Any], action: str, prompt: str, workdir: Path, session: dict[str, Any] | None, ephemeral: bool, fork_session: bool, commands: list[str], timeout: int) -> tuple[int, str, str]:
    launcher = str(profile.get("launcher", "claude"))
    command = [launcher, "-p", prompt, "--output-format", "json", "--permission-mode", "dontAsk"]
    tools = initial_toolset(action, commands)
    allowed_tools = tools.copy()
    if action == "execute":
        if commands:
            allowed_tools.extend(f"Bash({item})" for item in commands)
    command.extend(["--tools", ",".join(tools), "--allowed-tools", ",".join(allowed_tools)])
    if session and not ephemeral:
        command.extend(["--resume", str(session["session_id"])])
        if fork_session:
            command.append("--fork-session")
    if ephemeral:
        command.append("--no-session-persistence")
    model = profile.get("model")
    if isinstance(model, str) and model and model != "user-configured":
        command.extend(["--model", model])
    environment = provider_environment(profile)
    environment["CLAUDE_CONFIG_DIR"] = str(profile["config_dir"])
    try:
        completed = subprocess.run(command, cwd=workdir, env=environment, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", f"Timed out after {timeout}s"
    return completed.returncode, completed.stdout, completed.stderr


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
    elif isinstance(service, str) and service:
        result = subprocess.run(["security", "find-generic-password", "-s", service, "-w"], capture_output=True, text=True)
        if result.returncode != 0:
            raise CollaborationError(f"Missing macOS Keychain password item: {service}")
        token = result.stdout.rstrip("\r\n")
        if not token:
            raise CollaborationError(f"macOS Keychain item is empty: {service}")
        environment["ANTHROPIC_AUTH_TOKEN"] = token
    return environment


def parse_result(stdout: str) -> dict[str, Any]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CollaborationError(f"Claude CLI did not return valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CollaborationError("Claude CLI JSON result must be an object.")
    return data


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
    return record


def bash_create_commands(paths: list[Path]) -> list[str]:
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


def parse_response_contract(result: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    raw = result.get("result")
    if not isinstance(raw, str):
        return None, ["result is not a JSON string"]
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


def compact_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in outcomes[:20]:
        record = {key: item[key] for key in ("type", "path", "command", "passed", "count") if key in item}
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
        "topic": record["topic"], "routing": record["routing"], "output_path": output_rel,
        "result_contract_failed": bool(contract_errors),
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


def evaluate_outcomes(outcomes: list[dict[str, Any]], changed: list[str], workdir: Path, validation_commands: list[str]) -> list[dict[str, Any]]:
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
                command = item.get("command")
                if not isinstance(command, str) or command not in validation_commands:
                    raise CollaborationError("command_succeeds must exactly match one --validation-command.")
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
    parser.add_argument("--task-type", choices=("code", "document", "research", "creative", "planning", "data", "file_operations", "personal_advice", "current_information"))
    parser.add_argument("--mode", choices=("analyze", "draft", "critique", "revise", "execute", "verify"))
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--ephemeral", action="store_true")
    parser.add_argument("--return-mode", choices=RETURN_MODES, default="compact", help="stdout shape; full CLI JSON always remains in local outputs.")
    parser.add_argument("--topic-goal", help="Short durable goal for the one-page topic state; never include secrets or a full handoff.")
    parser.add_argument("--stop-rule", help="Short durable stop rule for the one-page topic state.")
    args = parser.parse_args()
    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    started_monotonic = time.monotonic()
    action_modes = {"consult": "analyze", "continue": "analyze", "draft": "draft", "critique": "critique", "execute": "execute"}
    task_type = args.task_type or "planning"
    mode = args.mode or action_modes[args.action]
    log: dict[str, Any] = {"run_id": run_id, "started_at": now(), "action": args.action, "topic": args.topic, "task_type": task_type, "mode": mode, "return_mode": args.return_mode}
    try:
        if args.timeout < 1:
            raise CollaborationError("--timeout must be positive.")
        workdir = safe_workdir(args.working_directory)
        handoff_file = Path(args.handoff).resolve()
        handoff_rel = relative(handoff_file)
        if is_sensitive(handoff_rel) or not handoff_file.is_file():
            raise CollaborationError("Handoff must be a readable, non-sensitive project file.")
        handoff = handoff_file.read_text(encoding="utf-8")
        allow_paths = [normalize_allow_path(value) for value in args.allow_path]
        if args.action == "execute" and not allow_paths:
            raise CollaborationError("execute requires at least one --allow-path.")
        if args.action == "execute" and not args.expected_outcomes:
            raise CollaborationError("execute requires --expected-outcomes.")
        delete_paths = [normalize_allow_path(value) for value in args.allow_delete]
        binary_paths = [normalize_allow_path(value) for value in args.allow_binary_path]
        if any(not allowed(path, allow_paths) for path in delete_paths + binary_paths):
            raise CollaborationError("Delete/binary paths must be inside an --allow-path.")
        if args.action != "execute" and (allow_paths or delete_paths or binary_paths or args.allow_command or args.expected_outcomes or args.validation_command):
            raise CollaborationError("Execution paths, commands, and outcomes are only valid for execute.")
        if any("\n" in command or command.strip() in {"", "*"} for command in args.allow_command):
            raise CollaborationError("Each allowed command must be a non-empty single-line pattern.")
        if any("\n" in command or command.strip() == "" for command in args.validation_command):
            raise CollaborationError("Each validation command must be a non-empty single line.")
        outcomes = load_outcomes(Path(args.expected_outcomes).resolve()) if args.action == "execute" else []
        new_files = required_new_files(outcomes) if args.action == "execute" else []
        available = profiles()
        data = registry()
        metrics = valid_metrics(load_json(METRICS_FILE, {"schema_version": 1, "round_robin_cursor": {}, "events": []}))
        sessions = [item for item in data["sessions"] if isinstance(item, dict)]
        if args.session_key:
            session = find_session(args.session_key, sessions)
            provider = str(session["provider"])
            if args.provider != "auto" and args.provider != provider:
                raise CollaborationError("--provider conflicts with --session-key.")
            if session.get("working_directory") != str(workdir):
                raise CollaborationError("Session working directory differs from this invocation.")
            auto_selected = False
            route = {"basis": "explicit_session_key"}
        else:
            provider, session, auto_selected, route = select_provider(args.provider, args.topic, workdir, sessions, available, metrics, task_type, mode)
        if args.fork_session and (session is None or args.ephemeral):
            raise CollaborationError("--fork-session requires a resolved persistent active session and cannot be ephemeral.")
        profile = available.get(provider)
        if not profile:
            raise CollaborationError(f"Provider '{provider}' has no configured profile.")
        problem = profile_problem(profile)
        if problem:
            fallback = alternate_provider(provider, available) if args.provider == "auto" else None
            if fallback is None:
                raise CollaborationError(f"Provider profile is not ready: {problem}")
            provider, profile = fallback
            session = None
            log["profile_failover"] = provider
        log.update({"provider": provider, "auto_selected": auto_selected, "session_key": session.get("key") if session else None, "routing": route})

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
                elif capability.get("bash_create_fallback"):
                    commands.extend(command for command in bash_create_commands(new_files) if command not in commands)
                    log["creation_fallback"] = "exact_bash_create"
                else:
                    raise CollaborationError("Provider cannot create required output files with the verified toolset.")

        checkpoint: Path | None = None
        before: dict[str, str] = {}
        if args.action == "execute":
            checkpoint = copy_checkpoint(run_id)
            before = manifest(PROJECT_ROOT)
        prompt = build_prompt(args.action, args.topic, handoff, allow_paths, commands, args.return_mode)
        exit_code, stdout, stderr = invoke(profile, args.action, prompt, workdir, session, args.ephemeral, effective_fork, commands, args.timeout)
        log.update({"exit_code": exit_code, "stderr": stderr[-4000:]})

        if exit_code != 0:
            fallback = alternate_provider(provider, available) if args.provider == "auto" else None
            if fallback is None:
                if checkpoint:
                    restore_changed(before, manifest(PROJECT_ROOT), checkpoint)
                raise CollaborationError(f"Claude CLI failed with exit code {exit_code}: {stderr[-800:]}")
            if checkpoint:
                restore_changed(before, manifest(PROJECT_ROOT), checkpoint)
            failed_provider = provider
            provider, profile = fallback
            session = None
            exit_code, stdout, stderr = invoke(profile, args.action, prompt, workdir, None, args.ephemeral, False, commands, args.timeout)
            log.update({"provider_failover": {"from": failed_provider, "to": provider}, "exit_code": exit_code, "stderr": stderr[-4000:]})
            if exit_code != 0:
                if checkpoint:
                    restore_changed(before, manifest(PROJECT_ROOT), checkpoint)
                raise CollaborationError(f"Fallback Claude CLI failed with exit code {exit_code}: {stderr[-800:]}")
        result = parse_result(stdout)
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
            outcome_results = evaluate_outcomes(outcomes, changed, workdir, args.validation_command)
            after_validation = manifest(PROJECT_ROOT)
            changed = sorted(path for path in set(before) | set(after_validation) if before.get(path) != after_validation.get(path))
            deleted = [path for path in changed if path in before and path not in after_validation]
            binary = binary_changed_paths(changed)
            violations = [path for path in changed if is_sensitive(Path(path)) or not allowed(Path(path), allow_paths)]
            violations.extend(path for path in deleted if not allowed(Path(path), delete_paths))
            violations.extend(path for path in binary if not allowed(Path(path), binary_paths))
            violations = sorted(set(violations))
        outcome_failures = [item for item in outcome_results if not item.get("passed")]
        if outcome_failures:
            if checkpoint:
                restore_changed(before, manifest(PROJECT_ROOT), checkpoint)
            status = "failed"
        elif violations:
            if checkpoint:
                restore_changed(before, manifest(PROJECT_ROOT), checkpoint, set(violations))
            status = "needs_review"
        else:
            status = "completed"
        log.update({"status": status, "changed_files": changed, "deleted_files": deleted if checkpoint else [], "binary_files": binary if checkpoint else [], "restored_violations": violations, "outcome_results": outcome_results})
        duration_seconds = round(time.monotonic() - started_monotonic, 3)
        append_event(metrics, {
            "run_id": run_id, "timestamp": now(), "provider": provider, "model_profile": provider,
            "task_type": task_type, "mode": mode, "status": status, "duration_seconds": duration_seconds,
            "tool_refusal": bool(result.get("permission_denials")) or (exit_code == 0 and "not available" in str(result).lower()),
            "cost_usd": result.get("total_cost_usd") if isinstance(result.get("total_cost_usd"), (int, float)) else None,
            "rework_count": 0, "route_basis": route.get("basis"),
        })
        write_json(METRICS_FILE, metrics)
        response, contract_errors = parse_response_contract(result)
        output_file = output_path(run_id, "outputs")
        output_rel = str(output_file.relative_to(PROJECT_ROOT))
        result_record = {"run_id": run_id, "status": status, "provider": provider, "action": args.action, "task_type": task_type, "mode": mode, "routing": route, "topic": args.topic, "result": result, "changed_files": changed, "restored_violations": violations, "outcome_results": outcome_results, "return_mode": args.return_mode, "result_contract": {"valid": response is not None, "errors": contract_errors}}
        write_json(output_file, result_record)
        if not args.ephemeral and isinstance(result.get("session_id"), str):
            parent_key = session.get("key") if effective_fork and session else None
            if session is None or effective_fork:
                session = {"key": f"{args.topic}-{provider}-{uuid.uuid4().hex[:6]}", "topic": args.topic, "provider": provider, "model_profile": provider, "working_directory": str(workdir), "session_id": result["session_id"], "initial_toolset": initial_toolset(args.action, commands), "status": "active", "parent_key": parent_key, "created_at": now()}
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
