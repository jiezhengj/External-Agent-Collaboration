"""Small cross-process locked JSON store used by runtime state files."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class StateStoreError(RuntimeError):
    pass


@contextmanager
def locked(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    """Lock a sibling lock file; fail closed when the platform lock is absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    handle = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            # msvcrt.locking is byte-range based and requires a one-byte file.
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise StateStoreError("state_lock_timeout") from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except (AttributeError, OSError) as exc:
                raise StateStoreError("state_lock_unsupported") from exc
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (AttributeError, OSError):
            pass
        handle.close()


def load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateStoreError(f"state_persistence_failed: {path.name}") from exc


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise StateStoreError("state_persistence_failed") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def update(path: Path, default: Any, mutate, timeout_seconds: float = 10.0) -> Any:
    """Atomically load, mutate and save one JSON state document under one lock."""
    with locked(path, timeout_seconds):
        current = load(path, default)
        updated = mutate(current)
        save(path, updated)
        return updated


@contextmanager
def transaction(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    with locked(path, timeout_seconds):
        yield
