from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np


class TestPiiRedaction:
    def test_redact_image_applies_face_and_plate_blur(self):
        from app.ai.pii_redaction import redact_image

        image = np.zeros((120, 160, 3), dtype=np.uint8)
        face_blurrer = MagicMock()
        face_blurrer.is_loaded.return_value = True
        face_blurrer.detect_faces.return_value = [(10, 10, 40, 40)]
        face_blurrer.blur_faces.side_effect = lambda img: img

        plate_blurrer = MagicMock()
        plate_blurrer.is_loaded.return_value = True
        plate_blurrer.detect_plates.return_value = [(80, 60, 120, 90)]
        plate_blurrer.blur_plates.side_effect = lambda img: img

        with (
            patch("app.ai.face_privacy.get_face_blurrer", return_value=face_blurrer),
            patch("app.ai.plate_privacy.get_plate_blurrer", return_value=plate_blurrer),
        ):
            _, faces, plates = redact_image(image)

        assert faces == 1
        assert plates == 1
        face_blurrer.blur_faces.assert_called_once()
        plate_blurrer.blur_plates.assert_called_once()

    def test_scan_image_counts_detections(self):
        from app.ai.pii_redaction import scan_image

        image = np.zeros((80, 80, 3), dtype=np.uint8)
        face_blurrer = MagicMock()
        face_blurrer.is_loaded.return_value = True
        face_blurrer.detect_faces.return_value = [(1, 2, 3, 4), (5, 6, 7, 8)]

        plate_blurrer = MagicMock()
        plate_blurrer.is_loaded.return_value = True
        plate_blurrer.detect_plates.return_value = [(10, 10, 20, 20)]

        with (
            patch("app.ai.face_privacy.get_face_blurrer", return_value=face_blurrer),
            patch("app.ai.plate_privacy.get_plate_blurrer", return_value=plate_blurrer),
        ):
            result = scan_image(image)

        assert result.faces == 2
        assert result.plates == 1

    def test_quad_to_bbox_adds_padding(self):
        from app.ai.plate_privacy import _quad_to_bbox

        det = np.array([20, 20, 80, 20, 80, 40, 20, 40, 0.9], dtype=np.float64)
        x1, y1, x2, y2 = _quad_to_bbox(det, 200, 120, padding_pct=0.1)
        assert x1 < 20
        assert y1 < 20
        assert x2 > 80
        assert y2 > 40

    def test_redact_export_image_bytes_uses_unified_pipeline(self):
        from app.ai.pii_redaction import RedactionResult, redact_export_image_bytes

        with patch(
            "app.ai.pii_redaction.redact_image_bytes",
            return_value=RedactionResult(image_bytes=b"redacted", faces_blurred=1, plates_blurred=2),
        ) as mock_redact:
            result = redact_export_image_bytes(b"raw")

        mock_redact.assert_called_once_with(b"raw", blur_faces=True, blur_plates=True)
        assert result.image_bytes == b"redacted"
        assert result.faces_blurred == 1
        assert result.plates_blurred == 2
