"""Generic utilities used across modules."""
from __future__ import annotations

from typing import Any, Optional


def optional_int(value: Any) -> Optional[int]:
    """Convert *value* to :class:`int` if possible, otherwise return ``None``."""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
