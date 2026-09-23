from __future__ import annotations

import re


class SensitiveRedactor:
    """Redacts passwords, tokens, API keys, and sensitive headers from logs and traces."""

    PATTERNS = [
        (
            re.compile(
                r'(?i)(password|secret|passwd|token|api[_-]?key)["\']?\s*[:=]\s*["\']?([^"\'\s,;]+)', re.IGNORECASE
            ),
            r"\1=***REDACTED***",
        ),
        (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE), r"Bearer ***REDACTED***"),
        (re.compile(r"(?i)ghp_[a-zA-Z0-9]{36}", re.IGNORECASE), r"ghp_***REDACTED***"),
        (re.compile(r"(?i)sk-[a-zA-Z0-9]{32,}", re.IGNORECASE), r"sk-***REDACTED***"),
    ]

    @classmethod
    def redact_text(cls, text: str) -> str:
        if not text:
            return ""
        result = text
        for pattern, replacement in cls.PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    @classmethod
    def redact_dict(cls, data: dict) -> dict:
        redacted = {}
        for k, v in data.items():
            if isinstance(v, str):
                redacted[k] = cls.redact_text(v)
            elif isinstance(v, dict):
                redacted[k] = cls.redact_dict(v)
            elif isinstance(v, list):
                redacted[k] = [cls.redact_text(item) if isinstance(item, str) else item for item in v]
            else:
                redacted[k] = v
        return redacted
