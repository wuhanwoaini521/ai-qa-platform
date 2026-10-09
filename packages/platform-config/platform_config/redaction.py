from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr

_SENSITIVE_QUERY_KEY = re.compile(r"password|passwd|pwd|token|secret|api[_-]?key|credential", re.IGNORECASE)


def _redact_url(value: str) -> str:
    if "://" not in value:
        return value
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    netloc = f"***@{parts.netloc.rsplit('@', 1)[1]}" if "@" in parts.netloc else parts.netloc
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = (
        urlencode([(key, "***" if _SENSITIVE_QUERY_KEY.search(key) else item) for key, item in query_pairs])
        if any(_SENSITIVE_QUERY_KEY.search(key) for key, _ in query_pairs)
        else parts.query
    )
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def sanitize_config_value(value: Any) -> Any:
    if isinstance(value, SecretStr):
        return "***" if value.get_secret_value() else ""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return _redact_url(value)
    if isinstance(value, dict):
        return {key: sanitize_config_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_config_value(item) for item in value]
    return value
