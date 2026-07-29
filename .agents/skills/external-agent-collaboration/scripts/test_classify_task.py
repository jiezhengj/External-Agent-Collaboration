#!/usr/bin/env python3
"""Local regression tests for deterministic delegation classification."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("classify_task.py")
SPEC = importlib.util.spec_from_file_location("classify_task", SCRIPT)
assert SPEC and SPEC.loader
classifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(classifier)


def expect(text: str, **expected: str) -> None:
    actual = classifier.classify(text)
    for key, value in expected.items():
        if actual[key] != value:
            raise AssertionError(f"{text!r}: expected {key}={value!r}, got {actual}")


def main() -> None:
    expect("帮我修改这个多文件 TypeScript bug，并运行测试", task_type="code", mode="execute", delegation="external_agent")
    expect("查询今天上海天气", task_type="current_information", delegation="native_codex")
    expect("Analyze the current docs structure", delegation="direct")
    expect("生成一份带图片的 PPTX", delegation="native_codex")
    expect("这里有 API token，请分析它", risk="prohibited", delegation="direct")
    expect("把这句话改得更通顺", delegation="direct")
    print("task-classification tests passed")


if __name__ == "__main__":
    main()
