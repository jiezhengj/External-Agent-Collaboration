#!/usr/bin/env python3
"""Classify a request before deciding whether to use an external collaborator."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from sensitivity import classify_sensitive_text
from request_envelope import RequestEnvelopeError, parse as parse_request_envelope


TASK_TYPES = ("code", "document", "research", "creative", "planning", "data", "file_operations", "personal_advice", "current_information")
MODES = ("analyze", "draft", "critique", "revise", "execute", "verify")


def contains(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def efficiency_fields(result: dict[str, str | float], text: str) -> dict[str, str | float | bool]:
    size = len(text.encode("utf-8"))
    large = result.get("context_size") == "large"
    return {"estimated_input_bytes": size, "estimated_return_bytes": min(8192, max(512, size // 5)), "return_ratio": round(min(8192, max(512, size // 5)) / max(size, 1), 4), "batchable": bool(large and result.get("risk") != "prohibited" and result.get("task_type") in {"document", "data", "research"}), "recommended_return_mode": "file_only" if large else "compact", "review_policy": "exception" if result.get("risk") == "high" else "none", "token_policy": "batch" if large else "delegate" if result.get("delegation") == "external_agent" else "direct"}

def classify(text: str) -> dict[str, str | float | bool]:
    envelope, normalized = parse_request_envelope(text)
    if not normalized:
        raise ValueError("Request text is empty.")

    if envelope is not None:
        sensitive = classify_sensitive_text(normalized)
        if sensitive.state != "safe" or envelope["sensitive"]:
            return {"task_type": "file_operations", "mode": "analyze", "risk": "requires_redaction" if sensitive.state != "prohibited" else "prohibited", "context_size": "small", "tool_requirement": "none", "delegation": "direct", "reason": "Structured request is sensitive or marked sensitive; external delegation is denied.", "confidence": 0.99}
        task_type = envelope["task_type"]
        mode = envelope["mode"]
        independent = bool(envelope.get("independent_review"))
        return {"task_type": task_type, "mode": mode, "risk": "high" if task_type == "code" and mode in {"execute", "verify"} else "medium" if mode == "execute" else "low", "context_size": envelope.get("context_size", "small"), "tool_requirement": "read_only" if mode in {"analyze", "critique", "verify"} else "file_edit", "delegation": "external_agent" if independent or mode in {"execute", "critique"} else "direct", "reason": "Structured request envelope takes precedence over keyword inference.", "confidence": 0.99, "structured": True}

    sensitive = classify_sensitive_text(normalized)
    current = contains(normalized, ("今天", "最新", "实时", "新闻", "天气", "股价", "汇率", "latest", "today", "weather", "price")) and not contains(normalized, ("current implementation", "current code", "当前实现", "当前代码"))
    connector = contains(normalized, ("gmail", "邮箱", "日历", "calendar", "slack", "notion", "drive"))
    artifact = contains(normalized, ("图片", "image", "ppt", "pptx", "幻灯片", "slides", "xlsx", "excel", "word", ".docx", "pdf"))
    code = contains(normalized, ("代码", "code", "bug", "报错", "test", "测试", "函数", "api", "重构", "repo", "仓库", "脚本"))
    data = contains(normalized, ("csv", "数据集", "dataset", "统计", "sql", "表格", "dataframe"))
    document = contains(normalized, ("文档", "文章", "markdown", "写作", "改写", "润色", "提纲", "prD"))
    creative = contains(normalized, ("创意", "文案", "品牌", "海报", "故事", "brainstorm", "copywriting"))
    planning = contains(normalized, ("计划", "方案", "roadmap", "规划", "决策", "比较"))
    personal = contains(normalized, ("生活", "个人", "建议", "习惯", "旅行", "情绪"))
    execute = contains(normalized, ("修改", "创建", "删除", "实现", "写入", "执行", "修复", "生成文件", "edit", "create", "implement", "fix"))
    critique = contains(normalized, ("审查", "评审", "批评", "review", "critique", "检查"))
    verify = contains(normalized, ("验证", "核实", "verify", "validate", "测试是否"))

    if sensitive.state == "prohibited":
        return {"task_type": "file_operations", "mode": "analyze", "risk": "prohibited", "context_size": "small", "tool_requirement": "none", "delegation": "direct", "reason": "Request contains credential material, an environment-file body, or explicit customer/production-data egress.", "confidence": 0.95}
    if sensitive.state == "requires_redaction":
        return {"task_type": "file_operations", "mode": "analyze", "risk": "requires_redaction", "context_size": "small", "tool_requirement": "none", "delegation": "direct", "reason": "Request references possible sensitive material; redact or replace it before external delegation.", "confidence": 0.8}
    if current or connector:
        return {"task_type": "current_information" if current else "research", "mode": "analyze", "risk": "medium", "context_size": "small", "tool_requirement": "native_codex", "delegation": "native_codex", "reason": "Request depends on timely or connected-account data.", "confidence": 0.9}
    if artifact:
        return {"task_type": "document" if document else "creative", "mode": "execute" if execute else "draft", "risk": "medium", "context_size": "medium", "tool_requirement": "native_codex", "delegation": "native_codex", "reason": "Final artifact should use a native Codex creation tool.", "confidence": 0.85}

    task_type = "code" if code else "data" if data else "creative" if creative else "planning" if planning else "personal_advice" if personal else "document" if document else "file_operations" if execute else "planning"
    mode = "verify" if verify else "critique" if critique else "execute" if execute else "draft" if task_type in {"document", "creative", "planning"} else "analyze"
    context_size = "large" if contains(normalized, ("全部", "大量", "几十", "所有文件", "whole repo", "many files", "long context")) else "medium" if len(normalized) > 500 else "small"
    risk = "high" if task_type == "code" and mode in {"execute", "verify"} else "medium" if mode == "execute" else "low"
    tool_requirement = "shell" if task_type == "code" and mode == "execute" else "file_edit" if mode == "execute" else "read_only"
    worthwhile = context_size == "large" or mode in {"critique", "execute"} or contains(normalized, ("第二意见", "独立", "外部模型", "协作"))
    delegation = "external_agent" if worthwhile else "direct"
    reason = "Bounded local execution, large local context, or independent review benefits from collaboration." if worthwhile else "Task appears small enough for Codex to handle directly."
    return {"task_type": task_type, "mode": mode, "risk": risk, "context_size": context_size, "tool_requirement": tool_requirement, "delegation": delegation, "reason": reason, "confidence": 0.65}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = Path(args.request_file).resolve()
    try:
        source = path.read_text(encoding="utf-8")
        result = classify(source)
        result.update(efficiency_fields(result, source))
    except (OSError, ValueError) as exc:
        print(str(exc))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
