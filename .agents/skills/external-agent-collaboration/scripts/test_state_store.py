#!/usr/bin/env python3
"""Atomic JSON persistence and local lock tests."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from state_store import StateStoreError, load, locked, save, transaction, update


def main() -> None:
    missing = Path(tempfile.gettempdir()) / "state-store-missing-does-not-exist.json"
    assert load(missing, {"default": True}) == {"default": True}
    with tempfile.TemporaryDirectory(prefix="state-store-errors-") as directory:
        root = Path(directory)
        invalid = root / "invalid.json"
        invalid.write_text("not-json", encoding="utf-8")
        try:
            load(invalid, {})
        except StateStoreError as exc:
            assert str(exc).startswith("state_persistence_failed")
        else:
            raise AssertionError("invalid JSON must fail closed")
        with patch("state_store.tempfile.NamedTemporaryFile", side_effect=OSError("no temp")):
            try:
                save(root / "save-error.json", {"x": 1})
            except StateStoreError as exc:
                assert str(exc) == "state_persistence_failed"
            else:
                raise AssertionError("save failure must be normalized")
        with patch("state_store.os.replace", side_effect=OSError("replace")):
            try:
                save(root / "replace-error.json", {"x": 1})
            except StateStoreError:
                pass
            else:
                raise AssertionError("replace failure must be normalized")
        with transaction(root / "transaction.json"):
            pass

    def locking_ok(*_args: object) -> None:
        return None

    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking_ok)
    with tempfile.TemporaryDirectory(prefix="state-store-windows-branch-") as directory:
        path = Path(directory) / "state.json"
        with patch.dict(sys.modules, {"msvcrt": fake_msvcrt}), patch("state_store.os.name", "nt"):
            with locked(path):
                pass

        def always_blocking(*_args: object) -> None:
            raise OSError("busy")

        fake_timeout = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=always_blocking)
        with patch.dict(sys.modules, {"msvcrt": fake_timeout}), patch("state_store.os.name", "nt"), patch("state_store.time.monotonic", side_effect=[0.0, 1.0]):
            try:
                with locked(path, timeout_seconds=0.0):
                    pass
            except StateStoreError as exc:
                assert str(exc) == "state_lock_timeout"
            else:
                raise AssertionError("Windows lock timeout must be surfaced")

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
