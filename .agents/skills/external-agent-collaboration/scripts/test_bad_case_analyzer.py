#!/usr/bin/env python3
"""Bad-case aggregation regression."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from analyze_bad_cases import analyze


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="bad-case-analyzer-") as directory:
        root = Path(directory)
        (root / "a.json").write_text(json.dumps({"error_code": "provider_timeout", "stage": "invocation", "host_platform": "macos", "selected_harness": "claude_code", "selected_provider": "deepseek", "skill_revision": "runtime:2.0.0", "occurred_at": "2026-08-05T00:00:00Z"}), encoding="utf-8")
        result = analyze(root)
        assert result["total"] == 1 and result["by_error_code"]["provider_timeout"] == 1
    print("bad-case-analyzer tests passed")


if __name__ == "__main__":
    main()
