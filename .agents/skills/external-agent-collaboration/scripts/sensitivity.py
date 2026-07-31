"""Detect sensitive handoff material without treating policy text as a secret."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SensitivityFinding:
    """A deliberately value-free classification for logs and user-facing errors."""

    state: str
    categories: tuple[str, ...] = ()


SAFE = SensitivityFinding("safe")

# Concrete token formats; the size floor avoids matching prose such as "sk-example".
CONCRETE_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}\b"),
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
)
ASSIGNMENT_PATTERN = re.compile(
    r"(?im)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)|"
    r"(?:api[_ -]?key|access[_ -]?token|auth[_ -]?token|password|secret))\s*[:=]\s*(.+?)\s*$"
)
ENV_HEADER_PATTERN = re.compile(r"(?im)^\s*(?:contents?\s+of\s+)?(?:an?\s+)?\.env(?:\.[\w-]+)?\s*[:：]?\s*$")
ENV_ASSIGNMENT_PATTERN = re.compile(r"(?m)^\s*(?:export\s+)?[A-Z][A-Z0-9_]*\s*=\s*\S+")
EXPLICIT_EXTERNAL_DATA_PATTERN = re.compile(
    r"(?is)(?:send|share|upload|外发|发送|上传|提供).{0,80}(?:customer|client|客户|生产(?:数据|数据库)|production\s+(?:data|database))"
)
POTENTIAL_SENSITIVE_REFERENCE = re.compile(
    r"(?:api[_ -]?(?:key|token)|access[_ -]?token|auth[_ -]?token|password|secret|credential|"
    r"\.env|private\s+key|客户数据|生产数据|密钥|私钥|密码)",
    re.IGNORECASE,
)
NEGATED_SENSITIVE_REFERENCE = re.compile(
    r"(?:do not|don't|never|禁止|不得|不要|不应|勿).{0,160}(?:api[_ -]?(?:key|token)|access[_ -]?token|"
    r"auth[_ -]?token|password|secret|credential|\.env|private\s+key|客户数据|生产数据|密钥|私钥|密码)",
    re.IGNORECASE,
)
PLACEHOLDER_VALUE = re.compile(
    r"(?i)^(?:\$\{?\w+\}?|<[^>]+>|\[[^\]]+\]|(?:your|example|redacted|masked|placeholder|dummy)[-_\w ]*|\*+)$"
)


def _assignment_has_real_value(text: str) -> bool:
    for match in ASSIGNMENT_PATTERN.finditer(text):
        value = match.group(2).strip().strip("'\"")
        if value and not PLACEHOLDER_VALUE.fullmatch(value):
            return True
    return False


def _contains_env_body(text: str) -> bool:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if ENV_HEADER_PATTERN.fullmatch(line):
            following = "\n".join(lines[index + 1:index + 8])
            if ENV_ASSIGNMENT_PATTERN.search(following):
                return True
    return False


def classify_sensitive_text(text: str) -> SensitivityFinding:
    """Return safe, requires_redaction, or prohibited without preserving values.

    The function is intentionally conservative at the final handoff boundary. A
    policy statement such as "do not send a token" is safe; a real token or an
    attached environment-file body is prohibited. An unresolved reference asks
    the caller to redact before it can be sent to any external harness.
    """
    if any(pattern.search(text) for pattern in CONCRETE_SECRET_PATTERNS):
        return SensitivityFinding("prohibited", ("credential_value_or_private_key",))
    if _assignment_has_real_value(text):
        return SensitivityFinding("prohibited", ("credential_assignment",))
    if _contains_env_body(text):
        return SensitivityFinding("prohibited", ("environment_file_body",))
    if EXPLICIT_EXTERNAL_DATA_PATTERN.search(text):
        return SensitivityFinding("prohibited", ("customer_or_production_data_egress",))

    if POTENTIAL_SENSITIVE_REFERENCE.search(text):
        # Explicit negation/policy wording remains safe; it describes a guard,
        # rather than supplying data that could leave the host.
        if NEGATED_SENSITIVE_REFERENCE.search(text):
            return SAFE
        return SensitivityFinding("requires_redaction", ("unresolved_sensitive_reference",))
    return SAFE
