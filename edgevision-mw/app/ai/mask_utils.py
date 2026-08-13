"""Mask rasterization and COCO RLE encoding utilities."""
from __future__ import annotations

import numpy as np

from app.core.logging import get_logger

logger = get_logger("edgevision.mask_utils")

_PYCOCOTOOLS_AVAILABLE: bool | None = None


def pycocotools_available() -> bool:
    """Return True when pycocotools is importable."""
    global _PYCOCOTOOLS_AVAILABLE
    if _PYCOCOTOOLS_AVAILABLE is None:
        try:
            import pycocotools.mask  # noqa: F401

            _PYCOCOTOOLS_AVAILABLE = True
        except ImportError:
            _PYCOCOTOOLS_AVAILABLE = False
    return _PYCOCOTOOLS_AVAILABLE


def polygon_to_mask(polygon: list, width: int, height: int) -> np.ndarray:
    """Rasterize a normalized polygon ``[[x,y], ...]`` to a binary mask."""
    import cv2

    mask = np.zeros((height, width), dtype=np.uint8)
    if not polygon or width <= 0 or height <= 0:
        return mask
    pts = np.array(
        [[round(p[0] * width), round(p[1] * height)] for p in polygon],
        dtype=np.int32,
    )
    if pts.shape[0] >= 3:
        cv2.fillPoly(mask, [pts], 1)
    return mask


def mask_to_rle(mask: np.ndarray) -> str:
    """Encode a binary mask as a COCO RLE string.

    Raises ``ImportError`` when pycocotools is not installed.
    """
    try:
        from pycocotools import mask as mask_utils
    except ImportError as exc:
        raise ImportError("pycocotools is required for RLE encoding") from exc

    rle = mask_utils.encode(np.asfortranarray((mask > 0).astype(np.uint8)))
    counts = rle["counts"]
    return counts.decode("ascii") if isinstance(counts, bytes) else counts


def polygon_to_mask_rle(polygon: list, width: int, height: int) -> str:
    """Rasterize a normalized polygon and return its COCO RLE encoding."""
    mask = polygon_to_mask(polygon, width, height)
    if not mask.any():
        raise ValueError("polygon produces an empty mask")
    return mask_to_rle(mask)
