#!/usr/bin/env python3
"""Cover local quality, maintenance and platform helper branches."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import coverage_gate
import execute_antigravity_isolated
import install_global
import probe_capabilities
import process_support
import quality_gate
import review_execution


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="quality-surfaces-") as directory:
        root = Path(directory)
        script_root = root / "scripts"
        script_root.mkdir()

        (script_root / "good.py").write_text("value = 1\n", encoding="utf-8")
        (script_root / "bad.py").write_text("if True shell=True:\n    pass\n", encoding="utf-8")
        (script_root / "broken.py").write_text("if :\n", encoding="utf-8")
        (script_root / "test_ignored.py").write_text("shell=True\n", encoding="utf-8")
        with patch.object(quality_gate, "SCRIPT_ROOT", script_root), patch.object(quality_gate, "ROOT", root):
            assert quality_gate.ast_errors()
            policy = quality_gate.source_policy_errors()
            assert any("shell=True" in item for item in policy)
            assert all("test_ignored" not in item for item in policy)
            with patch.object(quality_gate.subprocess, "run", side_effect=OSError("no git")):
                assert quality_gate.privacy_errors() == []

        code = root / "sample.py"
        code.write_text("x = 1\n", encoding="utf-8")
        counts_dir = root / "counts"
        counts_dir.mkdir()
        (counts_dir / "one.json").write_text(json.dumps({"sample.py:1": 1, "sample.py:9": 2}), encoding="utf-8")
        (counts_dir / "two.json").write_text(json.dumps({"sample.py:1": 3}), encoding="utf-8")
        assert coverage_gate.collect_counts(counts_dir)["sample.py:1"] == 4
        report = coverage_gate.report_from_counts({"good.py:1": 1})
        assert report["total"]["executable"] >= 1
        assert coverage_gate.threshold_errors({"total": {"percent": 0}, "modules": {"workspace_context.py": {"percent": 0}}})
        with patch.object(coverage_gate.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")):
            exit_code, generated, errors = coverage_gate.run()
            assert exit_code == 0 and isinstance(generated["modules"], dict) and errors
        report_path = root / "coverage.json"
        with patch.object(coverage_gate, "run", return_value=(0, report, "")), patch.object(sys, "argv", ["coverage_gate.py", "--report", str(report_path)]):
            assert coverage_gate.main() == 0
        assert report_path.is_file()

        source = root / "external-agent-collaboration"
        source.mkdir()
        (source / "SKILL.md").write_text("# fixture\n", encoding="utf-8")
        target = root / "global" / "skill"
        assert not install_global.same_source(target, source)
        install_global.apply(source, target)
        assert install_global.same_source(target, source)
        assert install_global.check(source, target)["samefile"] is True

        assert process_support._text(None) == ""
        assert process_support._text(b"ok") == "ok"
        with patch.object(process_support.os, "name", "nt"), patch.object(process_support.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True):
            assert "creationflags" in process_support._creation_options()
        with patch.object(process_support.os, "name", "posix"):
            assert process_support._creation_options() == {"start_new_session": True}
        fake = SimpleNamespace(pid=12, poll=lambda: None, send_signal=lambda *_: None, terminate=lambda: None, kill=lambda: None)
        with patch.object(process_support.os, "name", "nt"), patch.object(process_support.subprocess, "run") as run_mock:
            process_support._signal_process_group(fake, hard=True)
            assert run_mock.called
        with patch.object(process_support.os, "name", "posix"), patch.object(process_support.os, "killpg") as killpg:
            process_support._signal_process_group(fake, hard=False)
            killpg.assert_called_once()
        with patch.object(process_support.os, "name", "nt"), patch.object(process_support.signal, "CTRL_BREAK_EVENT", 1, create=True):
            process_support._signal_process_group(fake, hard=False)
        communicator = SimpleNamespace(communicate=lambda timeout=None: (b"out", b"err"))
        assert process_support._communicate(communicator, 1) == ("out", "err")

        assert probe_capabilities.read_json(root / "missing.json", {"ok": True}) == {"ok": True}
        json_path = root / "value.json"
        probe_capabilities.write_json(json_path, {"ok": True})
        assert probe_capabilities.read_json(json_path, {})["ok"] is True
        with patch.object(probe_capabilities.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="claude 1\n")):
            assert probe_capabilities.cli_version({"launcher": "claude"}) == "claude 1"
        with patch.object(probe_capabilities.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="")):
            assert probe_capabilities.cli_version({"launcher": "claude"}) == "unavailable"
        current = probe_capabilities.now()
        assert probe_capabilities.fresh({"host_platform": probe_capabilities.host_platform(), "profile_fingerprint": "fp", "claude_cli_version": "v", "checked_at": current}, "fp", "v", 1)

        with patch.object(execute_antigravity_isolated, "load_profiles", return_value={}), patch.object(
            sys, "argv", ["execute_antigravity_isolated.py", "--handoff", "missing.md", "--target", "docs/x.md", "--expected", "x"]
        ):
            try:
                execute_antigravity_isolated.main()
            except SystemExit as exc:
                assert "trusted explicit" in str(exc)
            else:
                raise AssertionError("untrusted isolated profile must fail closed")

        review_root = root / "review"
        control = review_root / ".ai-collaboration"
        (control / "outputs").mkdir(parents=True)
        (control / "handoffs").mkdir()
        record = {"status": "completed", "action": "execute", "provider": "provider_a", "topic": "surface", "changed_files": [], "outcome_results": []}
        (control / "outputs" / "run-1.json").write_text(json.dumps(record), encoding="utf-8")
        completed = SimpleNamespace(returncode=0, stdout="approved", stderr="")
        with patch.object(review_execution, "ROOT", review_root), patch.object(review_execution, "CONTROL", control), patch.object(review_execution.subprocess, "run", return_value=completed):
            assert review_execution.main.__name__ == "main"
            with patch.object(review_execution.sys, "argv", ["review_execution.py", "--run-id", "run-1", "--provider", "provider_b"]):
                assert review_execution.main() == 0
            review = json.loads((control / "reviews" / "run-1.json").read_text(encoding="utf-8"))
            assert review["reviewer"] == "provider_b" and review["exit_code"] == 0

    print("quality-maintenance surface tests passed")


if __name__ == "__main__":
    main()
