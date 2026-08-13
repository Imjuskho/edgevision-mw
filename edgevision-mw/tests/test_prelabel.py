"""Tests for Phase 8.2 — server-side pre-labeling."""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image


def _make_test_image(width: int = 640, height: int = 480, color: tuple = (128, 128, 128)) -> bytes:
    """Create a minimal JPEG image in memory."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_mock_onnx_session(class_idx: int = 0, confidence: float = 0.8):
    """Create a mock ONNX session that returns a specific class prediction."""
    probs = np.zeros(10, dtype=np.float32)
    probs[class_idx] = confidence

    session = MagicMock()
    input_info = MagicMock()
    input_info.name = "images"
    session.get_inputs.return_value = [input_info]
    session.run.return_value = [probs[np.newaxis, ...]]

    return session


class TestPrelabelService:
    """Test the pre-label service functions."""

    def test_prelabel_image_returns_empty_on_no_model(self):
        from app.services.prelabel import prelabel_image

        with patch("app.services.prelabel._find_model", return_value=None):
            result = prelabel_image(b"fake_image_bytes")
            assert result == []

    def test_prelabel_image_decodes_jpeg(self):
        from app.services.prelabel import prelabel_image

        img_bytes = _make_test_image()
        mock_session = _make_mock_onnx_session(class_idx=0, confidence=0.9)

        with (
            patch("app.services.prelabel._find_model", return_value=MagicMock(exists=lambda: True)),
            patch("onnxruntime.InferenceSession", return_value=mock_session),
        ):
            result = prelabel_image(img_bytes, confidence_threshold=0.3, grid_step=320)

            assert isinstance(result, list)
            assert len(result) >= 1
            for det in result:
                assert "label" in det
                assert "confidence" in det
                assert "bbox" in det
                assert len(det["bbox"]) == 4

    def test_prelabel_image_maps_classes_to_taxonomy(self):
        from app.services.prelabel import CLASS_NAMES, YOLO_TO_TAXONOMY, prelabel_image

        img_bytes = _make_test_image()

        for class_idx, class_name in enumerate(CLASS_NAMES):
            mock_session = _make_mock_onnx_session(class_idx=class_idx, confidence=0.9)

            with (
                patch("app.services.prelabel._find_model", return_value=MagicMock(exists=lambda: True)),
                patch("onnxruntime.InferenceSession", return_value=mock_session),
            ):
                result = prelabel_image(img_bytes, confidence_threshold=0.3, grid_step=320)

                if result:
                    expected_label = YOLO_TO_TAXONOMY.get(class_name, "car_private")
                    assert result[0]["label"] == expected_label
                    break

    def test_prelabel_image_respects_confidence_threshold(self):
        from app.services.prelabel import prelabel_image

        img_bytes = _make_test_image()
        mock_session = _make_mock_onnx_session(class_idx=0, confidence=0.2)

        with (
            patch("app.services.prelabel._find_model", return_value=MagicMock(exists=lambda: True)),
            patch("onnxruntime.InferenceSession", return_value=mock_session),
        ):
            result = prelabel_image(img_bytes, confidence_threshold=0.5, grid_step=320)
            assert result == []

    def test_prelabel_image_handles_corrupt_image(self):
        from app.services.prelabel import prelabel_image

        with patch("app.services.prelabel._find_model", return_value=MagicMock(exists=lambda: True)):
            result = prelabel_image(b"not_a_real_image")
            assert result == []

    def test_prelabel_image_bbox_normalized(self):
        from app.services.prelabel import prelabel_image

        img_bytes = _make_test_image(width=800, height=600)
        mock_session = _make_mock_onnx_session(class_idx=0, confidence=0.9)

        with (
            patch("app.services.prelabel._find_model", return_value=MagicMock(exists=lambda: True)),
            patch("onnxruntime.InferenceSession", return_value=mock_session),
        ):
            result = prelabel_image(img_bytes, confidence_threshold=0.3, grid_step=400)

            for det in result:
                x, y, w, h = det["bbox"]
                assert 0 <= x <= 1
                assert 0 <= y <= 1
                assert 0 < w <= 1
                assert 0 < h <= 1

    def test_nms_removes_overlapping_boxes(self):
        from app.services.prelabel import _nms

        boxes = [
            [0.1, 0.1, 0.3, 0.3],
            [0.12, 0.12, 0.32, 0.32],
            [0.5, 0.5, 0.7, 0.7],
        ]
        scores = [0.9, 0.85, 0.7]
        keep = _nms(boxes, scores, iou_thresh=0.3)
        assert len(keep) == 2
        assert 0 in keep
        assert 2 in keep


class TestPrelabelAPI:
    """Test the pre-label API endpoint."""

    @pytest.mark.asyncio
    async def test_prelabel_requires_auth(self, test_client):
        resp = await test_client.post(
            "/api/v1/studio/prelabel/image",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_prelabel_rejects_non_image(self, test_client, jwt_token_factory):
        token = jwt_token_factory(role="ADMIN")
        resp = await test_client.post(
            "/api/v1/studio/prelabel/image",
            files={"file": ("test.txt", b"not an image", "text/plain")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_prelabel_rejects_oversized_file(self, test_client, jwt_token_factory):
        token = jwt_token_factory(role="ADMIN")
        big_content = b"x" * (21 * 1024 * 1024)
        resp = await test_client.post(
            "/api/v1/studio/prelabel/image",
            files={"file": ("big.jpg", big_content, "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_prelabel_returns_detections(self, test_client, jwt_token_factory):
        token = jwt_token_factory(role="ADMIN")
        img_bytes = _make_test_image()
        mock_session = _make_mock_onnx_session(class_idx=0, confidence=0.9)

        with (
            patch("app.services.prelabel._find_model", return_value=MagicMock(exists=lambda: True)),
            patch("onnxruntime.InferenceSession", return_value=mock_session),
        ):
            resp = await test_client.post(
                "/api/v1/studio/prelabel/image",
                files={"file": ("test.jpg", img_bytes, "image/jpeg")},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "detections" in data
            assert "count" in data

    @pytest.mark.asyncio
    async def test_prelabel_existing_image_creates_annotation(self, test_client, db_session, mock_minio, jwt_token_factory):
        import hashlib
        from uuid import uuid4

        from app.models.annotation import Annotation
        from app.models.dataset import Dataset
        from app.models.enums import DatasetStatus

        # Create dataset
        ds = Dataset(
            dataset_id=f"ds{uuid4().hex[:8]}",
            name="Test Dataset",
            version="1.0",
            status=DatasetStatus.READY,
            sample_count=0,
            classes={},
            annotations_per_image=0.0,
            image_width=0,
            image_height=0,
            geographic_coverage={},
            demographic_report={},
            consent_coverage_pct=0.0,
            pii_scrub_verified=False,
            iaa_score=0.0,
            formats=[],
            price_usd=0,
            license_type="ANNUAL",
        )
        db_session.add(ds)
        await db_session.flush()

        # Prepare image record
        _make_test_image(64, 64)
        record = Image.new("RGB", (64, 64), color=(0, 0, 255))
        buf = io.BytesIO()
        record.save(buf, format="JPEG")
        buf.seek(0)
        img_data = buf.getvalue()

        from app.models.image import ImageRecord as IR

        image_record = IR(
            id=uuid4(),
            storage_key=f"datasets/{ds.dataset_id}/images/{uuid4().hex}.jpg",
            thumbnail_key=f"datasets/{ds.dataset_id}/thumbnails/{uuid4().hex}.jpg",
            filename="test.jpg",
            content_type="image/jpeg",
            size_bytes=len(img_data),
            width=64,
            height=64,
            source="file",
            dataset_id=ds.id,
            uploaded_by=None,
            tenant_id=None,
            checksum_sha256=hashlib.sha256(img_data).hexdigest(),
        )
        db_session.add(image_record)
        await db_session.commit()

        mock_minio.get_object.return_value.read.return_value = img_data

        token = jwt_token_factory(role="ADMIN")
        with patch("app.core.dependencies._minio_client", mock_minio):
            resp = await test_client.post(
                f"/api/v1/studio/prelabel/image/{image_record.id}/run",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "detections" in data

        # Verify an Annotation was created
        from sqlalchemy import select
        ann = (await db_session.execute(select(Annotation).where(Annotation.image_path == image_record.storage_key))).scalar_one_or_none()
        assert ann is not None
