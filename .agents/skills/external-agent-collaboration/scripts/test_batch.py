#!/usr/bin/env python3
"""Local regression tests for batch planning, reducer validation, and resume records."""
from __future__ import annotations
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("batch.py")
SPEC = importlib.util.spec_from_file_location("batch", SCRIPT)
assert SPEC and SPEC.loader
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)


def main() -> None:
    temporary = Path(tempfile.mkdtemp(prefix="batch-source-", dir=batch.ROOT))
    control = batch.ROOT / ".ai-collaboration"
    control.mkdir(exist_ok=True)
    runtime = Path(tempfile.mkdtemp(prefix="batch-test-", dir=control))
    try:
        source = temporary / "input"; source.mkdir()
        (source / "a.md").write_text("alpha", encoding="utf-8")
        (source / "b.md").write_text("beta", encoding="utf-8")
        (source / "blob.md").write_bytes(b"\0not text")
        records, skipped = batch.manifest(source, ["*.md"], "v1")
        assert len(records) == 2 and skipped and skipped[0]["reason"] == "binary"
        groups = batch.chunks(records, 1, 1024)
        assert len(groups) == 2
        output = runtime / "run"; batch.write_jsonl(output / "manifest.jsonl", records)
        results = runtime / "results"; results.mkdir()
        good = {**records[0], "status": "completed", "conclusion": "ok", "evidence_paths": [records[0]["source_relative_path"]]}
        bad = {**records[1], "status": "failed", "error_code": "parse_error"}
        batch.write_jsonl(results / "batch-0000.jsonl", [good, bad])
        class Args: pass
        args = Args(); args.manifest = str(output / "manifest.jsonl"); args.results_dir = str(results); args.output_dir = str(output / "reduced"); args.sample_size = 1
        assert batch.reduce(args) == 0
        summary = json.loads((output / "reduced" / "summary.json").read_text())
        assert summary["completed_records"] == 1 and summary["pending_records"] == 1
        assert len(batch.read_jsonl(output / "reduced" / "pending.jsonl")) == 1
        batch.write_jsonl(results / "batch-0001.jsonl", [{**records[0], "status": "completed"}])
        assert batch.reduce(args) == 0
        assert json.loads((output / "reduced" / "summary.json").read_text())["exception_records"] == 1
        print("batch tests passed")
    finally:
        shutil.rmtree(temporary)
        shutil.rmtree(runtime)

if __name__ == "__main__": main()
