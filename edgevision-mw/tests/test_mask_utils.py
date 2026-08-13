from __future__ import annotations

import numpy as np
import pytest


class TestMaskUtils:
    def test_polygon_to_mask_8x8(self):
        from app.ai.mask_utils import polygon_to_mask

        polygon = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        mask = polygon_to_mask(polygon, 8, 8)
        assert mask.shape == (8, 8)
        assert mask.sum() > 0

    def test_polygon_to_mask_rle_round_trip_8x8(self):
        pytest.importorskip("pycocotools")
        from pycocotools import mask as mask_utils

        from app.ai.mask_utils import polygon_to_mask, polygon_to_mask_rle

        polygon = [[0.125, 0.125], [0.875, 0.125], [0.875, 0.875], [0.125, 0.875]]
        mask = polygon_to_mask(polygon, 8, 8)
        rle_str = polygon_to_mask_rle(polygon, 8, 8)
        assert rle_str

        rle = {"size": [8, 8], "counts": rle_str.encode("ascii") if isinstance(rle_str, str) else rle_str}
        decoded = mask_utils.decode(rle)
        assert decoded.shape == (8, 8)
        assert decoded.sum() == mask.sum()

    def test_mask_to_rle_raises_without_pycocotools(self):
        from app.ai import mask_utils as mu

        mask = np.ones((4, 4), dtype=np.uint8)
        if mu.pycocotools_available():
            rle = mu.mask_to_rle(mask)
            assert rle
        else:
            with pytest.raises(ImportError):
                mu.mask_to_rle(mask)
