from __future__ import annotations

from typing import Any


def approval_granted(outputs: dict[str, Any]) -> bool:
    return outputs.get("approval", {}).get("approved") is True
