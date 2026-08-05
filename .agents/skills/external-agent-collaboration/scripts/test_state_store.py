#!/usr/bin/env python3
"""Atomic JSON persistence and local lock tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from state_store import StateStoreError, load, locked, save, update


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="state-store-") as directory:
        path = Path(directory) / "state.json"
        with locked(path):
            save(path, {"counter": 1})
        assert load(path, {}) == {"counter": 1}
        assert json.loads(path.read_text(encoding="utf-8"))["counter"] == 1
        with locked(path):
            save(path, {"counter": 2})
        assert load(path, {})["counter"] == 2
        update(path, {"counter": 0}, lambda value: {"counter": value["counter"] + 1})
        assert load(path, {})["counter"] == 3
    print("state-store tests passed")


if __name__ == "__main__":
    main()
