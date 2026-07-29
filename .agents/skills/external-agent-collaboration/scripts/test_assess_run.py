#!/usr/bin/env python3
"""Local regression test for manual quality/adoption metric updates."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("assess_run.py")
SPEC = importlib.util.spec_from_file_location("assess_run", SCRIPT)
assert SPEC and SPEC.loader
assess = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assess)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        assess.METRICS = Path(directory) / "metrics.json"
        assess.METRICS.write_text(json.dumps({"events": [{"run_id": "run-1"}]}), encoding="utf-8")
        previous = sys.argv
        try:
            sys.argv = ["assess_run.py", "--run-id", "run-1", "--quality-score", "4.5", "--user-adopted", "true", "--rework-count", "1"]
            assert assess.main() == 0
        finally:
            sys.argv = previous
        event = json.loads(assess.METRICS.read_text(encoding="utf-8"))["events"][0]
        assert event == {"run_id": "run-1", "quality_score": 4.5, "user_adopted": True, "rework_count": 1}
    print("assess-run tests passed")


if __name__ == "__main__":
    main()
