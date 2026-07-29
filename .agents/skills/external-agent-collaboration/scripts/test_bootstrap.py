#!/usr/bin/env python3
"""Regression test for minimal local collaboration-state initialization."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("bootstrap.py")
SPEC = importlib.util.spec_from_file_location("bootstrap", SCRIPT)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def main() -> None:
    original = bootstrap.ROOT, bootstrap.CONTROL, bootstrap.EXAMPLE, bootstrap.LOCAL
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        control = root / ".ai-collaboration"
        control.mkdir()
        example = control / "providers.local.example.json"
        example.write_text('{"provider_a": {}}\n', encoding="utf-8")
        bootstrap.ROOT, bootstrap.CONTROL, bootstrap.EXAMPLE, bootstrap.LOCAL = root, control, example, control / "providers.local.json"
        try:
            assert bootstrap.initialize() == 0
            assert (control / "project-context.md").is_file()
            assert (control / "decisions.md").is_file()
            assert (control / "topics").is_dir()
            assert bootstrap.check() == 0
        finally:
            bootstrap.ROOT, bootstrap.CONTROL, bootstrap.EXAMPLE, bootstrap.LOCAL = original
    print("bootstrap tests passed")


if __name__ == "__main__":
    main()
