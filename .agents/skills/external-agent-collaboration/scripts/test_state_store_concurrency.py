#!/usr/bin/env python3
"""Cross-process state-store contention test (200 successful updates)."""

from __future__ import annotations

import concurrent.futures
import json
import multiprocessing
import tempfile
from pathlib import Path

from state_store import update


def increment(path_value: str) -> int:
    path = Path(path_value)
    update(path, {"count": 0}, lambda value: {"count": int(value.get("count", 0)) + 1}, timeout_seconds=30)
    return 1


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="state-store-concurrency-") as directory:
        path = Path(directory) / "counter.json"
        context = multiprocessing.get_context("spawn")
        with concurrent.futures.ProcessPoolExecutor(max_workers=8, mp_context=context) as pool:
            completed = list(pool.map(increment, [str(path)] * 200))
        value = json.loads(path.read_text(encoding="utf-8"))
        assert len(completed) == 200 and sum(completed) == 200
        assert value["count"] == 200, value
    print("state-store concurrency passed: 200/200")


if __name__ == "__main__":
    main()
