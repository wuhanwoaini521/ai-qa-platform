from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit


class SensitiveRedactor:
    """Redacts credentials, personal identifiers, and sensitive metadata from logs and traces."""

    SENSITIVE_KEYS = re.compile(
        r"(?i)(?:^|[_-])(authorization|cookie|set-cookie|password|passwd|secret|token|api[_-]?key"
        r"|email(?:[_-]?(?:address|addr))?|phone(?:[_-]?(?:number|no))?"
        r"|telephone(?:[_-]?(?:number|no))?|mobile(?:[_-]?(?:phone|number))?"
        r"|cell(?:[_-]?(?:phone|number))?|ssn|social[_-]?security(?:[_-]?number)?)(?:$|[_-])"
    )
    REDACTION_PLACEHOLDER_PATTERN = re.compile(
        r"(?i)(?:\*{3}\s*REDACTED\s*\*{3}|\[\s*REDACTED(?:[_ -][A-Z0-9_-]+)?\s*\]"
        r"|<\s*REDACTED(?:[_ -][A-Z0-9_-]+)?\s*>)"
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
        (re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "[REDACTED_EMAIL]"),
        (
            re.compile(
                r"(?<!\w)(?:\d{3}[-. \u00a0\u202f\u2010-\u2015\u2212]\d{2}[-. \u00a0\u202f\u2010-\u2015\u2212]\d{4}|\d{9})(?!\w)"
            ),
            "[REDACTED_SSN]",
        ),
        (
            re.compile(
                r"(?<!\w)(?:\+?1[ .\u00a0\u202f\u2010-\u2015\u2212-]?)?(?:\(\d{3}\)|\d{3})"
                r"[ .\u00a0\u202f\u2010-\u2015\u2212-]?\d{3}[ .\u00a0\u202f\u2010-\u2015\u2212-]?\d{4}"
                r"(?:\s*(?:ext\.?|x)\s*\d{1,6})?(?!\w)",
                re.IGNORECASE,
            ),
            "[REDACTED_PHONE]",
        ),
    ]

    @classmethod
    def contains_redaction_placeholder(cls, text: str) -> bool:
        """Return whether text contains a persisted redaction marker."""
        return bool(text and cls.REDACTION_PLACEHOLDER_PATTERN.search(text))

    @classmethod
    def redact_text(cls, text: str) -> str:
        if not text:
            return ""
        result = cls.URL_PATTERN.sub(lambda match: cls.redact_url(match.group(0)), text)
        for pattern, replacement in cls.PATTERNS:
            result = pattern.sub(replacement, result)
        return result

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
                normalized_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key_text)
                normalized_key = re.sub(r"[^A-Za-z0-9_-]+", "_", normalized_key)
                if cls.SENSITIVE_KEYS.search(normalized_key):
                    redacted[key] = "***REDACTED***" if item is not None else None
                else:
                    redacted[key] = cls.redact_value(item)
            return redacted
        if isinstance(value, (list, tuple)):
            return [cls.redact_value(item) for item in value]
        if isinstance(value, str):
            return cls.redact_text(value)
        return value
