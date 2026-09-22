"""Helpers for JSON/JSONB-safe Python values (e.g. before PostgreSQL writes)."""

from __future__ import annotations

from typing import Any


def json_safe(value: Any) -> Any:
    """Recursively convert numpy scalars/arrays to native Python JSON types."""
    if value is None:
        return None

    # Lazy import so callers without numpy pay no import cost.
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        np = None  # type: ignore[assignment]

    if np is not None:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()

    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]

    return value
