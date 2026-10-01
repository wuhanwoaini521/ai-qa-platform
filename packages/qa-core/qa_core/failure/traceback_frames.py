"""Utilities for mapping pytest tracebacks to editable project source locations."""

from __future__ import annotations

import re
from pathlib import Path

_FRAME_PATTERNS = (
    re.compile(r"""File\s+["'](?P<path>.+?\.py)["'],\s+line\s+(?P<line>\d+)"""),
    re.compile(r"""(?P<path>(?:[A-Za-z]:)?[^\s\r\n]*?\.py):(?P<line>\d+)(?=[:\s]|$)"""),
)

_FRAME_EXCLUDES = {"site-packages", "dist-packages", "pytest", "playwright", "pluggy"}


def last_user_code_frame(stack_trace: str, workspace_dir: Path | str) -> tuple[str, int] | None:
    """Return the deepest existing Python frame under a workspace as ``(relative_path, line)``.

    Pytest's compact and long traceback formats are both accepted. Frames from interpreter and
    third-party internals are filtered by workspace containment and common dependency directories.
    """
    workspace = Path(workspace_dir).resolve()
    frames: list[tuple[str, int]] = []
    for line in stack_trace.splitlines():
        for pattern in _FRAME_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            raw_path = match.group("path").strip(" \t'\"")
            line_number = int(match.group("line"))
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = workspace / candidate
            try:
                resolved = candidate.resolve()
                relative = resolved.relative_to(workspace)
            except (OSError, ValueError):
                continue
            if resolved.suffix.lower() != ".py" or not resolved.is_file() or line_number < 1:
                continue
            if any(part.lower() in _FRAME_EXCLUDES for part in relative.parts):
                continue
            frames.append((relative.as_posix(), line_number))
            break
    return frames[-1] if frames else None
