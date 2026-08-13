"""Tests for road segmenter model path resolution and inference geometry."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


class TestResolveRoadSegModelPath:
    def test_returns_explicit_path_when_valid(self, tmp_path: Path):
        model = tmp_path / "road.onnx"
        model.write_bytes(b"onnx")

        from app.ai.road_segmenter import resolve_road_seg_model_path

        with patch("app.ai.road_segmenter.is_valid_road_seg_model", return_value=True):
            assert resolve_road_seg_model_path(str(model)) == str(model)

    def test_returns_none_when_no_candidates_exist(self):
        from app.ai.road_segmenter import resolve_road_seg_model_path

        with (
            patch("app.core.config.settings") as mock_settings,
            patch("app.ai.road_segmenter.is_valid_road_seg_model", return_value=False),
        ):
            mock_settings.ROAD_SEG_MODEL_PATH = ""
            assert resolve_road_seg_model_path(None) is None

    def test_prefers_configured_road_seg_path(self, tmp_path: Path):
        model = tmp_path / "configured.onnx"
        model.write_bytes(b"onnx")

        from app.ai.road_segmenter import resolve_road_seg_model_path

        with (
            patch("app.core.config.settings") as mock_settings,
            patch("app.ai.road_segmenter.is_valid_road_seg_model", return_value=True),
        ):
            mock_settings.ROAD_SEG_MODEL_PATH = str(model)
            assert resolve_road_seg_model_path(None) == str(model)

    def test_rejects_coco_model(self, tmp_path: Path):
        coco = tmp_path / "coco.onnx"
        coco.write_bytes(b"coco")

        from app.ai.road_segmenter import is_valid_road_seg_model

        with patch("app.ai.road_segmenter.is_coco_seg_model", return_value=True):
            assert is_valid_road_seg_model(str(coco)) is False

    def test_rejects_pt_weights(self, tmp_path: Path):
        pt = tmp_path / "best.pt"
        pt.write_bytes(b"pt")

        from app.ai.road_segmenter import is_valid_road_seg_model

        assert is_valid_road_seg_model(str(pt)) is False


class TestLetterboxUndo:
    def test_model_to_orig_with_letterbox(self):
        from app.ai.road_segmenter import LetterboxParams, RoadSegmenter

        seg = RoadSegmenter.__new__(RoadSegmenter)
        seg._letterbox = LetterboxParams(scale=1.0, dx=0, dy=0, nw=640, nh=480, orig_w=640, orig_h=480)
        x1, y1, x2, y2 = seg._model_to_orig(320.0, 240.0, 100.0, 80.0)
        assert x1 == pytest.approx(270.0, abs=0.1)
        assert y1 == pytest.approx(200.0, abs=0.1)
        assert x2 == pytest.approx(370.0, abs=0.1)
        assert y2 == pytest.approx(280.0, abs=0.1)

    def test_mask_to_orig_crops_padding(self):
        from app.ai.road_segmenter import LetterboxParams, RoadSegmenter

        seg = RoadSegmenter.__new__(RoadSegmenter)
        seg._input_width = 640
        seg._input_height = 640
        seg._letterbox = LetterboxParams(scale=1.0, dx=100, dy=50, nw=440, nh=540, orig_w=440, orig_h=540)
        mask = np.zeros((640, 640), dtype=np.float32)
        mask[50:590, 100:540] = 1.0
        result = seg._mask_to_orig(mask)
        assert result.shape == (540, 440)
        assert result.mean() == pytest.approx(1.0, abs=0.01)


class TestIsCocoSegModel:
    def test_detects_coco_from_metadata(self, tmp_path: Path):
        from app.ai.road_segmenter import is_coco_seg_model

        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake-onnx")

        mock_session = MagicMock()
        mock_session.get_modelmeta.return_value.custom_metadata_map = {
            "description": "Ultralytics YOLOv8n-seg model trained on coco.yaml",
        }
        with patch("onnxruntime.InferenceSession", return_value=mock_session):
            assert is_coco_seg_model(str(model_path)) is True

    def test_accepts_road_metadata(self, tmp_path: Path):
        from app.ai.road_segmenter import is_coco_seg_model

        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake-onnx")

        mock_session = MagicMock()
        mock_session.get_modelmeta.return_value.custom_metadata_map = {
            "description": "Ultralytics YOLOv8n-seg model trained on road_dataset.yaml",
            "names": "{0: 'good_road', 1: 'pothole'}",
        }
        with patch("onnxruntime.InferenceSession", return_value=mock_session):
            assert is_coco_seg_model(str(model_path)) is False


class TestRoadSegmentEndpoint:
    @pytest.mark.asyncio
    async def test_segment_returns_503_when_no_road_model(self, test_client, db_session):
        from uuid import uuid4

        from app.core.security import create_access_token
        from app.models.annotation import Annotation
        from app.models.buyer import User
        from app.models.enums import AnnotationStatus, BatchStatus, NodeCategory, PIIMode
        from app.models.ingestion import IngestionBatch
        from app.models.node import Node

        user_id = uuid4()
        user = User(
            id=user_id,
            email=f"{user_id.hex[:8]}@test.com",
            hashed_password="fakehash",
            full_name="Road Test",
            role="ADMIN",
            is_active=True,
            dpa_signed=True,
        )
        db_session.add(user)

        node = Node(
            node_id=f"node-{uuid4().hex[:8]}",
            district="test",
            latitude=-13.0,
            longitude=33.0,
            category=NodeCategory.ROAD,
            hardware_profile={},
            network_config={},
            capture_schedule="daily_1200",
            interest_classes=["road"],
            pii_mode=PIIMode.NONE,
            firmware_version="1.0.0",
            status="ONLINE",
            public_key=b"\x00" * 32,
        )
        db_session.add(node)
        await db_session.flush()

        batch = IngestionBatch(
            batch_id=f"batch-{uuid4().hex[:8]}",
            node_id=node.id,
            hub_id="test-hub",
            event_count=1,
            file_size_bytes=1024,
            checksum_sha256="0" * 64,
            node_signature=b"\x01" * 64,
            compression_codec="none",
            quality_scores={},
            status=BatchStatus.INGESTED,
        )
        db_session.add(batch)
        await db_session.flush()

        ann_id = uuid4()
        ann = Annotation(
            id=ann_id,
            batch_id=batch.id,
            image_index=0,
            image_path="datasets/test/frame.jpg",
            thumbnail_path="datasets/test/frame_thumb.jpg",
            detected_objects={},
            auto_labels={},
            status=AnnotationStatus.PENDING,
            quality_score=0.8,
        )
        db_session.add(ann)
        await db_session.commit()

        token = create_access_token({"sub": str(user.id), "role": user.role})

        with (
            patch("app.api.road.get_minio_client") as mock_minio,
            patch("app.ai.road_segmenter.get_road_segmenter") as mock_get_seg,
        ):
            import io

            from PIL import Image

            buf = io.BytesIO()
            Image.new("RGB", (640, 480), (128, 128, 128)).save(buf, format="JPEG")
            buf.seek(0)
            mock_client = MagicMock()
            mock_client.get_object.return_value.read.return_value = buf.getvalue()
            mock_minio.return_value = mock_client

            mock_seg = MagicMock()
            mock_seg.is_loaded.return_value = False
            mock_get_seg.return_value = mock_seg

            resp = await test_client.post(
                "/api/v1/road/segment",
                json={"image_id": str(ann_id), "conf_threshold": 0.35, "iou_threshold": 0.45},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 503
        assert "COCO" in resp.json()["detail"] or "not available" in resp.json()["detail"]
