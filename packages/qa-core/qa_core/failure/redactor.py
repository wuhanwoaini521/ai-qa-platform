from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit


class SensitiveRedactor:
    """Redacts passwords, tokens, API keys, and sensitive headers from logs and traces."""

    SENSITIVE_KEYS = re.compile(
        r"(?i)(?:^|[_-])(authorization|cookie|set-cookie|password|passwd|secret|token|api[_-]?key)(?:$|[_-])"
    )
    URL_PATTERN = re.compile(r"(?i)https?://[^\s\"'<>]+")

    PATTERNS = [
        (
            re.compile(
                r'(?i)(authorization|proxy-authorization)(["\']?\s*[:=]\s*["\']?)(?:bearer|basic)\s+[^"\'\s,;]+'
            ),
            r"\1\2***REDACTED***",
        ),
        (
            re.compile(
                r'(?i)(authorization|cookie|set-cookie|password|secret|passwd|token|api[_-]?key)["\']?\s*[:=]\s*["\']?([^"\'\s,;]+)',
                re.IGNORECASE,
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
        return cls.URL_PATTERN.sub(lambda match: cls.redact_url(match.group(0)), result)

    @staticmethod
    def redact_url(value: str) -> str:
        """Remove credentials and query/fragment data before a URL reaches logs or traces."""
        raw = str(value or "")[:4096]
        try:
            parsed = urlsplit(raw)
            scheme = parsed.scheme.lower()
            if scheme in {"http", "https"} and parsed.hostname:
                hostname = parsed.hostname
                if ":" in hostname and not hostname.startswith("["):
                    hostname = f"[{hostname}]"
                try:
                    port = parsed.port
                except ValueError:
                    port = None
                netloc = f"{hostname}:{port}" if port is not None else hostname
                return urlunsplit((scheme, netloc, parsed.path, "", ""))[:2048]
            if scheme == "about":
                return f"about:{parsed.path}"[:2048]
            if scheme:
                # Data, blob, file and custom URLs may embed page contents or local paths.
                return f"{scheme}:"
            return urlunsplit(("", "", parsed.path, "", ""))[:2048]
        except (TypeError, ValueError):
            return ""

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
