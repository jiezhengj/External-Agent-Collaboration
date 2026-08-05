#!/usr/bin/env python3
"""Global link installer regression."""

from __future__ import annotations

import tempfile
from pathlib import Path

from install_global import apply, check


def main() -> None:
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="install-global-") as directory:
        target = Path(directory) / "skills" / "external-agent-collaboration"
        result = check(source, target)
        assert result["ok"] is True and result["target_exists"] is False
        apply(source, target)
        checked = check(source, target)
        assert checked["ok"] is True and checked["samefile"] is True
    print("install-global tests passed")


if __name__ == "__main__":
    main()
