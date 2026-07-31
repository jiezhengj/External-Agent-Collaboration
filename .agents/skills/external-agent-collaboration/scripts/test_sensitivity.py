#!/usr/bin/env python3
"""Regression tests for value-aware handoff sensitivity detection."""

from __future__ import annotations

from sensitivity import classify_sensitive_text

FAKE_TOKEN = "sk-" + "test_value_" * 3


def expect(text: str, state: str) -> None:
    actual = classify_sensitive_text(text)
    if actual.state != state:
        raise AssertionError(f"expected {state!r}, got {actual!r}")


def main() -> None:
    expect("The policy says: do not send a token or read .env files.", "safe")
    expect("Do not read or modify project files, run commands, access secrets, or invoke subagents.", "safe")
    expect("本系统禁止外发 token、密钥或 .env 内容。", "safe")
    expect("ANTHROPIC_AUTH_TOKEN=" + FAKE_TOKEN, "prohibited")
    expect("Authorization: Bearer abcdefghijklmnopQRSTUV", "prohibited")
    expect("-----BEGIN " + "PRIVATE KEY-----\nabc", "prohibited")
    expect("Contents of .env:\nAPP_MODE=production\nAPI_TOKEN=${LOCAL_TOKEN}", "prohibited")
    expect("Please upload this customer's production database export.", "prohibited")
    expect("Please assess an attached .env file after I redact it.", "requires_redaction")
    print("sensitivity tests passed")


if __name__ == "__main__":
    main()
