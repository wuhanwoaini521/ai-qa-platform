from __future__ import annotations

import re


class SensitiveRedactor:
    """Redacts passwords, tokens, API keys, and sensitive headers from logs and traces."""

    SENSITIVE_KEYS = re.compile(
        r"(?i)(?:^|[_-])(authorization|cookie|set-cookie|password|passwd|secret|token|api[_-]?key)(?:$|[_-])"
    )

    PATTERNS = [
        (
            re.compile(
                r'(?i)(authorization|cookie|set-cookie|password|secret|passwd|token|api[_-]?key)["\']?\s*[:=]\s*["\']?([^"\'\s,;]+)', re.IGNORECASE
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
        return cls.redact_value(data)

    @classmethod
    def redact_value(cls, value):
        """Recursively redact trace/log metadata, including values behind sensitive keys."""
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                key_text = str(key)
                if cls.SENSITIVE_KEYS.search(key_text):
                    redacted[key] = "***REDACTED***" if item is not None else None
                else:
                    redacted[key] = cls.redact_value(item)
            return redacted
        if isinstance(value, (list, tuple)):
            return [cls.redact_value(item) for item in value]
        if isinstance(value, str):
            return cls.redact_text(value)
        return value
