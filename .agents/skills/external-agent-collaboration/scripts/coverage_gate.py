#!/usr/bin/env python3
"""Run the dependency-free regression suite under the stdlib ``trace`` tool.

The regression suite launches many CLI scripts in child Python processes.  A
normal in-process ``trace.Trace`` run therefore misses the most important
paths.  This gate injects a tiny, temporary ``sitecustomize`` into every
Python process, writes one bounded count file per process, and aggregates the
files after the suite exits.  The temporary injector is never written to the
repository and the report contains only source-relative paths and counts.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent


SCRIPT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_ROOT.parents[3]
CONTROL_ROOT = PROJECT_ROOT / ".ai-collaboration"
REPORT_PATH = CONTROL_ROOT / "coverage" / "production-coverage.json"

# These are the v2 safety-critical modules.  Platform-specific fallback
# branches are measured and must be covered by the native CI job on that
# platform; they are not silently excluded here.
CORE_MODULES = (
    "workspace_context.py",
    "failure_events.py",
    "scope_guard.py",
    "state_store.py",
)
CORE_THRESHOLD = 90.0
TOTAL_THRESHOLD = 80.0

SITE_CUSTOMIZE = dedent(
    """
    from __future__ import annotations

    import atexit
    import json
    import os
    import sys
    from pathlib import Path
    from trace import Trace

    _source_root = Path(os.environ["EXT_AGENT_COVERAGE_SOURCE_ROOT"]).resolve()
    _output_root = Path(os.environ["EXT_AGENT_COVERAGE_OUTPUT_ROOT"])
    _tracer = Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
    _previous_trace = sys.gettrace()
    sys.settrace(_tracer.globaltrace)

    def _save() -> None:
        sys.settrace(_previous_trace)
        counts = {}
        for (filename, line_number), count in _tracer.results().counts.items():
            path = Path(filename).resolve()
            try:
                relative = path.relative_to(_source_root).as_posix()
            except ValueError:
                continue
            counts[f"{relative}:{line_number}"] = count
        _output_root.mkdir(parents=True, exist_ok=True)
        (_output_root / f"{os.getpid()}.json").write_text(json.dumps(counts), encoding="utf-8")

    atexit.register(_save)
    """
).lstrip()


def statement_lines(path: Path) -> set[int]:
    """Return source lines containing executable AST statements."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt) or not hasattr(node, "lineno"):
            continue
        # Module/function/class docstrings are metadata, not executable
        # implementation lines.  Excluding them matches trace's executable
        # line semantics and keeps the denominator honest.
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) and isinstance(node.value.value, str):
            continue
        lines.add(node.lineno)
    return lines


def collect_counts(directory: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in directory.glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        for key, count in value.items():
            if isinstance(key, str) and isinstance(count, int):
                counts[key] = counts.get(key, 0) + count
    return counts


def report_from_counts(counts: dict[str, int]) -> dict[str, object]:
    modules: dict[str, dict[str, object]] = {}
    total_lines = 0
    total_hit = 0
    for path in sorted(SCRIPT_ROOT.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        executable = statement_lines(path)
        hit = {
            int(key.rsplit(":", 1)[1])
            for key, count in counts.items()
            if count > 0 and key.rsplit(":", 1)[0] == path.name
        }
        covered = len(executable & hit)
        total_lines += len(executable)
        total_hit += covered
        modules[path.name] = {
            "covered": covered,
            "executable": len(executable),
            "percent": round((covered / len(executable) * 100) if executable else 100.0, 2),
            "uncovered_lines": sorted(executable - hit),
        }
    total_percent = (total_hit / total_lines * 100) if total_lines else 100.0
    return {
        "schema_version": 1,
        "tool": "stdlib.trace",
        "core_threshold_percent": CORE_THRESHOLD,
        "total_threshold_percent": TOTAL_THRESHOLD,
        "total": {"covered": total_hit, "executable": total_lines, "percent": round(total_percent, 2)},
        "modules": modules,
    }


def threshold_errors(report: dict[str, object]) -> list[str]:
    errors: list[str] = []
    total = report["total"]
    assert isinstance(total, dict)
    if float(total["percent"]) < TOTAL_THRESHOLD:
        errors.append(f"scripts coverage {total['percent']}% is below {TOTAL_THRESHOLD:.0f}%")
    modules = report["modules"]
    assert isinstance(modules, dict)
    for name in CORE_MODULES:
        item = modules.get(name)
        if not isinstance(item, dict):
            errors.append(f"missing coverage module {name}")
        elif float(item["percent"]) < CORE_THRESHOLD:
            errors.append(f"{name} coverage {item['percent']}% is below {CORE_THRESHOLD:.0f}%")
    return errors


def run() -> tuple[int, dict[str, object], str]:
    with tempfile.TemporaryDirectory(prefix="ext-agent-coverage-") as directory:
        temp = Path(directory)
        (temp / "sitecustomize.py").write_text(SITE_CUSTOMIZE, encoding="utf-8")
        counts_dir = temp / "counts"
        env = os.environ.copy()
        env["EXT_AGENT_COVERAGE_SOURCE_ROOT"] = str(SCRIPT_ROOT)
        env["EXT_AGENT_COVERAGE_OUTPUT_ROOT"] = str(counts_dir)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(temp), str(SCRIPT_ROOT), env.get("PYTHONPATH", "")]))
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_ROOT / "run_regression.py")],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        report = report_from_counts(collect_counts(counts_dir))
        report["regression_exit_code"] = completed.returncode
        if completed.returncode != 0:
            report["regression_output_tail"] = (completed.stderr or completed.stdout)[-1200:]
        return completed.returncode, report, "; ".join(threshold_errors(report))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(REPORT_PATH))
    parser.add_argument("--check", action="store_true", help="fail when regression or coverage thresholds fail")
    args = parser.parse_args()
    exit_code, report, errors = run()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload = {"ok": exit_code == 0 and not errors, "report": str(report_path), "errors": errors.split("; ") if errors else []}
    print(json.dumps(payload, ensure_ascii=False))
    if args.check and (exit_code != 0 or errors):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
