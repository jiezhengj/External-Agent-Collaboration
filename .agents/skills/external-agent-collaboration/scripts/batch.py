#!/usr/bin/env python3
"""Plan and reduce non-sensitive, resumable read-only document batches."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
CONTROL = ROOT / ".ai-collaboration"
SENSITIVE = {".git", ".ai-collaboration", "secrets", "credentials", "private"}
MAX_RECORD_BYTES = 4096


class BatchError(RuntimeError):
    pass


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BatchError(f"Invalid JSONL in {path} line {number}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise BatchError(f"JSONL record in {path} line {number} is not an object.")
        records.append(value)
    return records


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise BatchError(f"Path is outside project root: {path}") from exc


def permitted(path: Path) -> bool:
    return not any(part in SENSITIVE or part.startswith(".env") for part in Path(rel(path)).parts)


def local_control_path(path: Path) -> None:
    try:
        path.resolve().relative_to(CONTROL.resolve())
    except ValueError as exc:
        raise BatchError("Batch manifests and results must stay under ignored .ai-collaboration/.") from exc


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def is_text(path: Path) -> bool:
    try:
        return b"\0" not in path.read_bytes()[:8192]
    except OSError:
        return False


def manifest(input_root: Path, patterns: list[str], schema_version: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for path in sorted(input_root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = rel(path)
        if not permitted(path):
            skipped.append({"path": relative, "reason": "sensitive_or_controlled"})
            continue
        source_rel = path.relative_to(input_root).as_posix()
        if not any(fnmatch.fnmatch(source_rel, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
            continue
        if not is_text(path):
            skipped.append({"path": relative, "reason": "binary"})
            continue
        source_hash = digest(path)
        key = hashlib.sha256(f"{relative}\0{source_hash}\0{schema_version}".encode("utf-8")).hexdigest()
        records.append({"key": key, "source_relative_path": relative, "source_hash": source_hash, "size_bytes": path.stat().st_size, "media_type": path.suffix.lower() or "text/plain", "schema_version": schema_version})
    return records, skipped


def chunks(records: list[dict[str, Any]], max_files: int, max_bytes: int) -> list[list[dict[str, Any]]]:
    if max_files < 1 or max_bytes < 1:
        raise BatchError("max-files and max-bytes must be positive.")
    output: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    used = 0
    for record in records:
        size = int(record["size_bytes"])
        if current and (len(current) >= max_files or used + size > max_bytes):
            output.append(current)
            current, used = [], 0
        current.append(record)
        used += size
    if current:
        output.append(current)
    return output


def deterministic_sample(records: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    return sorted(records, key=lambda item: item["key"])[:max(0, count)]


def plan(args: argparse.Namespace) -> int:
    input_root = Path(args.input_root).resolve()
    if not input_root.is_dir() or not permitted(input_root):
        raise BatchError("input-root must be a non-sensitive directory inside the project.")
    output = Path(args.output_dir).resolve()
    rel(output); local_control_path(output)
    records, skipped = manifest(input_root, args.include, args.schema_version)
    groups = chunks(records, args.max_files, args.max_bytes)
    write_jsonl(output / "manifest.jsonl", records)
    for index, group in enumerate(groups):
        write_jsonl(output / "chunks" / f"batch-{index:04d}.jsonl", group)
    sample = deterministic_sample(records, args.sample_size)
    write_jsonl(output / "sample.jsonl", sample)
    atomic_json(output / "plan.json", {"schema_version": 1, "result_schema_version": args.schema_version, "input_root": rel(input_root), "patterns": args.include, "record_count": len(records), "input_bytes": sum(int(item["size_bytes"]) for item in records), "chunk_count": len(groups), "max_files": args.max_files, "max_bytes": args.max_bytes, "sample_count": len(sample), "skipped": skipped})
    print(json.dumps({"status": "planned", "output_dir": rel(output), "records": len(records), "chunks": len(groups), "sample": len(sample)}, ensure_ascii=False))
    return 0


def validate_result(item: dict[str, Any], expected: dict[str, Any]) -> str | None:
    for key in ("key", "source_relative_path", "source_hash", "schema_version"):
        if item.get(key) != expected.get(key):
            return f"{key}_mismatch"
    if item.get("status") not in {"completed", "failed", "skipped"}:
        return "invalid_status"
    for field in ("conclusion", "error_code"):
        if field in item and (not isinstance(item[field], str) or len(item[field].encode("utf-8")) > MAX_RECORD_BYTES):
            return f"invalid_{field}"
    return None


def reduce(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).resolve()
    result_dir = Path(args.results_dir).resolve()
    output = Path(args.output_dir).resolve()
    rel(manifest_path); rel(result_dir); rel(output)
    local_control_path(manifest_path); local_control_path(result_dir); local_control_path(output)
    expected = {item["key"]: item for item in read_jsonl(manifest_path)}
    accepted: dict[str, dict[str, Any]] = {}
    exceptions: list[dict[str, Any]] = []
    for path in sorted(result_dir.glob("batch-*.jsonl")):
        for item in read_jsonl(path):
            key = item.get("key")
            if not isinstance(key, str) or key not in expected:
                exceptions.append({"source": rel(path), "reason": "unknown_key"})
                continue
            if key in accepted:
                exceptions.append({"key": key, "source": rel(path), "reason": "duplicate_key"})
                continue
            reason = validate_result(item, expected[key])
            if reason:
                exceptions.append({"key": key, "source": rel(path), "reason": reason})
                continue
            accepted[key] = item
    completed = [item for item in accepted.values() if item["status"] == "completed"]
    failures = [item for item in accepted.values() if item["status"] != "completed"]
    pending = [item for key, item in expected.items() if key not in accepted or accepted[key]["status"] != "completed"]
    sample = deterministic_sample(completed, args.sample_size)
    write_jsonl(output / "index.jsonl", [accepted[key] for key in sorted(accepted)])
    write_jsonl(output / "pending.jsonl", pending)
    write_jsonl(output / "sample.jsonl", sample)
    write_jsonl(output / "exceptions.jsonl", exceptions)
    atomic_json(output / "summary.json", {"schema_version": 1, "manifest_records": len(expected), "accepted_records": len(accepted), "completed_records": len(completed), "failed_or_skipped_records": len(failures), "pending_records": len(pending), "exception_records": len(exceptions), "sample_records": len(sample), "complete": len(pending) == 0 and not exceptions})
    print(json.dumps({"status": "reduced", "output_dir": rel(output), "completed": len(completed), "pending": len(pending), "exceptions": len(exceptions)}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    planning = sub.add_parser("plan")
    planning.add_argument("--input-root", required=True)
    planning.add_argument("--output-dir", required=True)
    planning.add_argument("--include", action="append", default=["*.md"])
    planning.add_argument("--schema-version", default="v1")
    planning.add_argument("--max-files", type=int, default=25)
    planning.add_argument("--max-bytes", type=int, default=2 * 1024 * 1024)
    planning.add_argument("--sample-size", type=int, default=5)
    reducing = sub.add_parser("reduce")
    reducing.add_argument("--manifest", required=True)
    reducing.add_argument("--results-dir", required=True)
    reducing.add_argument("--output-dir", required=True)
    reducing.add_argument("--sample-size", type=int, default=5)
    args = parser.parse_args()
    try:
        return plan(args) if args.command == "plan" else reduce(args)
    except BatchError as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
