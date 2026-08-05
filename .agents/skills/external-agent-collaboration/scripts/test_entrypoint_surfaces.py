#!/usr/bin/env python3
"""Exercise local CLI entrypoint surfaces without provider or network calls."""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


def call(module: object, argv: list[str]) -> int:
    old = sys.argv
    sys.argv = [f"{getattr(module, '__name__', 'entrypoint')}.py", *argv]
    try:
        try:
            result = getattr(module, "main")()
            return int(result) if result is not None else 0
        except SystemExit as exc:
            return int(exc.code or 0)
    finally:
            sys.argv = old


def help_surface(module: object) -> None:
    old = sys.argv
    sys.argv = [f"{getattr(module, '__name__', 'entrypoint')}.py", "--help"]
    try:
        try:
            getattr(module, "main")()
        except SystemExit as exc:
            assert exc.code in (None, 0)
    finally:
        sys.argv = old


def main() -> None:
    archive = importlib.import_module("archive_session")
    maintain = importlib.import_module("maintain_runtime")
    migrate_runtime = importlib.import_module("migrate_runtime")
    migrate_harness = importlib.import_module("migrate_harness_state")
    trust_provider = importlib.import_module("trust_provider")
    trust_harness = importlib.import_module("trust_harness")
    execute_antigravity = importlib.import_module("execute_antigravity")
    consult_antigravity = importlib.import_module("consult_antigravity")
    probe = importlib.import_module("probe_capabilities")
    quality_gate = importlib.import_module("quality_gate")
    doctor = importlib.import_module("doctor")
    doctor_harness = importlib.import_module("doctor_harness")
    review_execution = importlib.import_module("review_execution")
    collaborate = importlib.import_module("collaborate")

    with tempfile.TemporaryDirectory(prefix="entrypoint-surfaces-") as directory:
        root = Path(directory)
        control = root / ".ai-collaboration"
        control.mkdir()

        sessions = control / "sessions.json"
        topics = control / "topics.json"
        session = {"key": "session-1", "status": "active", "topic": "topic-1", "provider": "provider_a", "model_profile": "profile_a", "working_directory": str(root)}
        sessions.write_text(json.dumps({"schema_version": 1, "sessions": [session]}), encoding="utf-8")
        topics.write_text(json.dumps({"schema_version": 1, "topics": [{"topic": "topic-1", "working_directory": str(root), "status": "active", "sessions": [{"key": "session-1", "status": "active"}]}]}), encoding="utf-8")
        with patch.object(archive, "ROOT", root), patch.object(archive, "CONTROL", control), patch.object(archive, "SESSIONS", sessions), patch.object(archive, "TOPICS", topics):
            assert call(archive, ["--session-key", "session-1"]) == 0
            assert (control / "archives" / "session-1.md").is_file()

        (control / "provider-metrics.json").write_text(json.dumps({"events": [{"status": "failed", "quality_score": 2}]}), encoding="utf-8")
        with patch.object(maintain, "ROOT", root), patch.object(maintain, "CONTROL", control):
            assert call(maintain, ["--days", "30"]) == 0

        runtime_files = {name: control / f"{name}.json" for name in ("sessions", "trust", "health", "capabilities", "metrics")}
        for name, path in runtime_files.items():
            if name == "metrics":
                payload = {"schema_version": 1, "events": []}
            elif name == "sessions":
                payload = {"schema_version": 1, "sessions": []}
            else:
                payload = {"schema_version": 1, "providers": {}}
            path.write_text(json.dumps(payload), encoding="utf-8")
        with patch.object(migrate_runtime, "PROJECT_ROOT", root), patch.object(migrate_runtime, "CONTROL_ROOT", control), patch.object(migrate_runtime, "SESSIONS_FILE", runtime_files["sessions"]):
            assert call(migrate_runtime, []) == 0
            assert call(migrate_runtime, ["--apply"]) == 0
        with patch.object(migrate_harness, "PROJECT_ROOT", root), patch.object(migrate_harness, "CONTROL_ROOT", control), patch.object(migrate_harness, "RUNTIME_FILES", runtime_files):
            assert call(migrate_harness, []) == 0

        profile = {"config_dir": str(root / "config"), "launcher": "claude"}
        trust = {"schema_version": 1, "providers": {}}
        with patch.object(trust_provider.collaborate, "profiles", return_value={"provider_a": profile}), patch.object(trust_provider.collaborate, "trust_registry", return_value=trust), patch.object(trust_provider.collaborate, "write_json", return_value=None):
            assert call(trust_provider, ["--provider", "provider_a", "--approve"]) == 0
            assert call(trust_provider, ["--provider", "provider_a", "--revoke"]) == 0

        harness_profiles = control / "harness-profiles.local.json"
        harness_profiles.write_text(json.dumps({"profiles": {"readonly": {"harness": "antigravity", "mode": "plan", "launcher": "agy"}}}), encoding="utf-8")
        with patch.object(trust_harness, "CONTROL_ROOT", control):
            assert call(trust_harness, ["--profile", "readonly", "--approve"]) == 0
            assert call(trust_harness, ["--profile", "readonly", "--revoke"]) == 0

        assert execute_antigravity.scope_allows([Path("docs/a.md")], ["docs"]) is True
        assert execute_antigravity.scope_allows([Path("private/a.md")], ["docs"]) is False
        assert execute_antigravity.full_auto_requires_isolation({"dangerously_skip_permissions": True}) is True
        assert execute_antigravity.full_auto_requires_isolation({}) is False
        with patch.object(consult_antigravity.collaborate, "session_matches_workspace", return_value=False):
            try:
                consult_antigravity.antigravity_session("missing", [], root)
            except consult_antigravity.collaborate.CollaborationError:
                pass
            else:
                raise AssertionError("missing Antigravity session must fail")

        assert probe.fresh(None, "fp", "v", 1) is False
        assert probe.fresh({"host_platform": "other", "profile_fingerprint": "fp", "claude_cli_version": "v", "checked_at": "2020-01-01T00:00:00+00:00"}, "fp", "v", 1) is False
        assert probe.fresh({"host_platform": probe.host_platform(), "profile_fingerprint": "fp", "claude_cli_version": "v", "checked_at": "not-a-date"}, "fp", "v", 1) is False
        assert review_execution.review_provider("provider_a", "provider_b") == "provider_b"
        assert "Independent execution critique" in review_execution.handoff_text({"topic": "t", "changed_files": [], "outcome_results": []})
        assert call(consult_antigravity, ["--action", "consult", "--topic", "t", "--handoff", "missing.md", "--timeout", "0"]) == 2
        assert call(execute_antigravity, ["--topic", "t", "--handoff", "missing.md", "--expected-outcomes", "missing.json", "--allow-path", "docs", "--timeout", "0"]) == 2
        assert call(importlib.import_module("route_harness"), ["--action", "consult", "--topic", "t", "--handoff", "missing.md", "--timeout", "0"]) == 2
        assert call(review_execution, ["--run-id", "missing-run", "--provider", "provider_b"]) == 2
        assert call(probe, ["--provider", "missing-provider"]) == 2

        with patch.object(quality_gate, "privacy_errors", return_value=[]):
            assert call(quality_gate, ["--privacy"]) == 0
        fake_profile = {"launcher": "definitely-not-installed", "config_dir": str(root / "missing"), "required_environment": []}
        with patch.object(doctor, "load_profiles", return_value={"provider_a": fake_profile}):
            assert doctor.check("provider_a")
        with patch.object(doctor_harness, "load_profiles", return_value={"readonly": {"harness": "antigravity", "mode": "plan", "launcher": "definitely-not-installed"}}), patch.object(doctor_harness, "harness_control", return_value=control):
            payload = doctor_harness.check("readonly")
            assert payload["ok"] is False

        response = {"summary": "fixture", "changed_files": [], "commands_run": [], "validation_results": [], "risks": [], "uncertainty": ""}
        handoff = root / "handoff.md"
        handoff.write_text("Read-only fixture review.", encoding="utf-8")
        registry = {"schema_version": 1, "sessions": []}

        class FakeConsultAdapter:
            def invoke(self, _request: object) -> tuple[int, str, str]:
                return 0, json.dumps({"conversation_id": "conversation-1", "status": "SUCCESS", "structured_output": response}), ""

            def parse_outer_result(self, stdout: str) -> dict[str, object]:
                return json.loads(stdout)

            def permission_state(self, _result: dict[str, object]) -> str:
                return "allowed"

        consult_patches = (
            patch.object(consult_antigravity, "load_profiles", return_value={"readonly": {"launcher": "agy", "mode": "plan"}}),
            patch.object(consult_antigravity, "trusted", return_value=True),
            patch.object(consult_antigravity, "AntigravityAdapter", FakeConsultAdapter),
            patch.object(consult_antigravity.collaborate, "safe_workdir", return_value=root),
            patch.object(consult_antigravity.collaborate, "PROJECT_ROOT", root),
            patch.object(consult_antigravity.collaborate, "CONTROL_ROOT", control),
            patch.object(consult_antigravity.collaborate, "SHARED_CONTROL_ROOT", control),
            patch.object(consult_antigravity.collaborate, "registry", return_value=registry),
            patch.object(consult_antigravity.collaborate, "save_registry", return_value=None),
            patch.object(consult_antigravity.collaborate, "topics_registry", return_value={"schema_version": 1, "topics": []}),
            patch.object(consult_antigravity.collaborate, "write_json", side_effect=lambda path, value: (Path(path).parent.mkdir(parents=True, exist_ok=True), Path(path).write_text(json.dumps(value), encoding="utf-8"))),
            patch.object(consult_antigravity.collaborate, "workspace_identity", return_value="fixture-workspace"),
        )
        with consult_patches[0], consult_patches[1], consult_patches[2], consult_patches[3], consult_patches[4], consult_patches[5], consult_patches[6], consult_patches[7], consult_patches[8], consult_patches[9], consult_patches[10]:
            assert call(consult_antigravity, ["--action", "consult", "--topic", "fixture-consult", "--handoff", str(handoff), "--working-directory", str(root), "--profile", "readonly", "--invocation-id", "inv-fixture"]) == 0

        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "target.md").write_text("target", encoding="utf-8")
        outcomes = root / "execute-outcomes.json"
        outcomes.write_text(json.dumps({"outcomes": [{"type": "file_exists", "path": "docs/target.md"}]}), encoding="utf-8")

        class FakeExecuteAdapter:
            def invoke(self, _request: object) -> tuple[int, str, str]:
                return 0, json.dumps({"status": "SUCCESS", "structured_output": response}), ""

            def parse_outer_result(self, stdout: str) -> dict[str, object]:
                return json.loads(stdout)

            def permission_state(self, _result: dict[str, object]) -> str:
                return "allowed"

            def classify_error(self, _code: int, _stderr: str) -> str:
                return ""

        execute_patches = (
            patch.object(execute_antigravity, "load_profiles", return_value={"execute": {"launcher": "agy", "mode": "accept-edits", "execution_scope": {"allowed_paths": ["docs"], "allowed_commands": []}}}),
            patch.object(execute_antigravity, "trusted", return_value=True),
            patch.object(execute_antigravity, "AntigravityAdapter", FakeExecuteAdapter),
            patch.object(execute_antigravity.collaborate, "safe_workdir", return_value=root),
            patch.object(execute_antigravity.collaborate, "PROJECT_ROOT", root),
            patch.object(execute_antigravity.collaborate, "CONTROL_ROOT", control),
        )
        with execute_patches[0], execute_patches[1], execute_patches[2], execute_patches[3], execute_patches[4], execute_patches[5]:
            assert call(execute_antigravity, ["--topic", "fixture-execute", "--handoff", str(handoff), "--expected-outcomes", str(outcomes), "--allow-path", "docs", "--profile", "execute", "--working-directory", str(root), "--invocation-id", "inv-execute"]) == 0

        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "a.txt").write_text("hello\n", encoding="utf-8")
        (root / "docs" / "value.json").write_text('{"ok": true}\n', encoding="utf-8")
        outcome_file = root / "outcomes.json"
        outcome_file.write_text(json.dumps({"outcomes": [{"type": "file_exists", "path": "docs/new.txt"}]}), encoding="utf-8")
        original_roots = {name: getattr(collaborate, name) for name in ("PROJECT_ROOT", "CONTROL_ROOT", "SHARED_CONTROL_ROOT", "GOALS_DIR")}
        try:
            collaborate.PROJECT_ROOT = root
            collaborate.CONTROL_ROOT = control
            collaborate.SHARED_CONTROL_ROOT = control
            collaborate.GOALS_DIR = control / "goals"
            assert collaborate.allowed(Path("docs/a.txt"), [Path("docs")]) is True
            try:
                collaborate.normalize_allow_path("../escape")
            except collaborate.CollaborationError:
                pass
            else:
                raise AssertionError("unsafe allow path must fail")
            assert collaborate.required_new_files(collaborate.load_outcomes(outcome_file)) == [root / "docs" / "new.txt"]
            assert collaborate.binary_changed_paths(["docs/a.txt"]) == []
            (root / "docs" / "binary.bin").write_bytes(b"prefix\0suffix")
            assert collaborate.binary_changed_paths(["docs/binary.bin"]) == ["docs/binary.bin"]
            assert collaborate.schema_errors({"ok": True}, {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}, "additionalProperties": False}) == []
            assert collaborate.schema_errors("", {"type": "string", "minLength": 1, "pattern": "x"})
            assert collaborate.schema_errors([], {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "integer"}})
            assert "construction_stage_report" in collaborate.response_contract_instruction("compact", "construction_stage_report")
            assert "JSON" in collaborate.response_contract_instruction("compact", "standard")
            results = collaborate.evaluate_outcomes([
                {"type": "file_exists", "path": "docs/a.txt"},
                {"type": "file_contains", "path": "docs/a.txt", "text": "hello"},
                {"type": "file_equals", "path": "docs/a.txt", "text": "hello\n"},
                {"type": "json_schema", "path": "docs/value.json", "schema": {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}},
                {"type": "changed_paths", "min": 1, "max": 2},
                {"type": "command_succeeds", "argv": [sys.executable, "-c", "pass"]},
                {"type": "unsupported"},
            ], ["docs/a.txt"], root, [], [[sys.executable, "-c", "pass"]])
            assert results[0]["passed"] and results[5]["passed"] and "error" in results[-1]
            assert collaborate.bash_create_commands([root / "docs" / "new.txt"])
            assert collaborate.write_topic_state("surface-test", root, "goal", "stop", "completed", "consult", [], "outputs/x.json")
            checkpoint = collaborate.copy_checkpoint("surface-test")
            assert checkpoint.is_dir()
            (root / "docs" / "a.txt").write_text("changed\n", encoding="utf-8")
            collaborate.restore_changed({"docs/a.txt": "before"}, {"docs/a.txt": "after"}, checkpoint)
            assert (root / "docs" / "a.txt").read_text(encoding="utf-8") == "hello\n"
        finally:
            for name, value in original_roots.items():
                setattr(collaborate, name, value)

    for name in (
        "analyze_bad_cases", "assess_run", "batch", "batch_worker", "bootstrap", "classify_task",
        "construction_protocol", "coverage_gate", "goal_lifecycle", "install_global", "migrate_harness_state",
        "migrate_portable_profiles", "migrate_runtime", "migrate_workspace_state", "probe_capabilities",
        "quality_gate", "review_execution", "route_harness", "trust_harness", "trust_provider",
    ):
        module = importlib.import_module(name)
        if hasattr(module, "main"):
            help_surface(module)

    print("entrypoint-surface tests passed")


if __name__ == "__main__":
    main()
