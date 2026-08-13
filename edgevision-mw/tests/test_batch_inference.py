"""Tests for dataset-level batch inference helpers and API."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import AnnotationStatus, BatchStatus, DatasetStatus, NodeCategory, PIIMode
from app.models.ingestion import IngestionBatch
from app.models.node import Node
from app.models.road_annotation import RoadAnnotation


async def _seed_dataset_with_annotations(db_session, count: int = 3):
    ds = Dataset(
        dataset_id=f"batch-{uuid4().hex[:8]}",
        name="Batch Test Dataset",
        version="1.0",
        status=DatasetStatus.READY,
        sample_count=count,
        classes={},
        annotations_per_image=0.0,
        image_width=640,
        image_height=480,
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
        event_count=count,
        file_size_bytes=1024,
        checksum_sha256="0" * 64,
        node_signature=b"\x01" * 64,
        compression_codec="none",
        quality_scores={},
        status=BatchStatus.INGESTED,
    )
    db_session.add(batch)
    await db_session.flush()

    annotations = []
    for idx in range(count):
        ann = Annotation(
            id=uuid4(),
            batch_id=batch.id,
            image_index=idx,
            image_path=f"datasets/{ds.dataset_id}/frame_{idx}.jpg",
            thumbnail_path=f"datasets/{ds.dataset_id}/frame_{idx}_thumb.jpg",
            detected_objects={"objects": []},
            auto_labels={"labels": []},
            status=AnnotationStatus.PENDING,
            quality_score=0.0,
            dataset_id=ds.id,
        )
        db_session.add(ann)
        annotations.append(ann)

    await db_session.commit()
    return ds, annotations


class TestBatchInferenceService:
    @pytest.mark.asyncio
    async def test_detection_remaining_skips_labeled(self, db_session):
        from app.services.batch_inference import resolve_batch_annotation_ids

        ds, annotations = await _seed_dataset_with_annotations(db_session, count=2)
        annotations[0].human_labels = {"labels": [{"label": "car_private"}]}
        await db_session.commit()

        ids, skipped = await resolve_batch_annotation_ids(
            db_session,
            ds.dataset_id,
            mode="detection",
            scope="remaining",
        )

        assert len(ids) == 1
        assert ids[0] == annotations[1].id
        assert skipped == 1

    @pytest.mark.asyncio
    async def test_road_remaining_skips_existing(self, db_session):
        from app.services.batch_inference import resolve_batch_annotation_ids

        ds, annotations = await _seed_dataset_with_annotations(db_session, count=2)
        db_session.add(
            RoadAnnotation(
                annotation_id=annotations[0].id,
                surface_type="paved",
                instances=[],
                model_version="test",
                auto_generated=True,
                reviewed=False,
            )
        )
        await db_session.commit()

        ids, skipped = await resolve_batch_annotation_ids(
            db_session,
            ds.dataset_id,
            mode="road",
            scope="remaining",
        )

        assert len(ids) == 1
        assert ids[0] == annotations[1].id
        assert skipped == 1


class TestPrelabelBatchAPI:
    @pytest.mark.asyncio
    async def test_prelabel_batch_requires_auth(self, test_client):
        resp = await test_client.post(
            "/api/v1/studio/prelabel/batch",
            json={"dataset_id": "missing"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_prelabel_batch_queues_job(self, test_client, db_session, jwt_token_factory):
        from unittest.mock import patch

        ds, _ = await _seed_dataset_with_annotations(db_session, count=2)
        token = jwt_token_factory(role="ADMIN")

        with patch("app.workers.tasks.auto_label_annotations_task") as mock_task:
            mock_task.apply_async.return_value = None
            resp = await test_client.post(
                "/api/v1/studio/prelabel/batch",
                json={"dataset_id": ds.dataset_id, "scope": "remaining"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_images"] == 2
        assert "job_id" in data
        mock_task.apply_async.assert_called_once()


class TestRoadBatchAPI:
    @pytest.mark.asyncio
    async def test_road_batch_returns_503_without_model(self, test_client, db_session, jwt_token_factory):
        from unittest.mock import MagicMock, patch

        ds, _ = await _seed_dataset_with_annotations(db_session, count=2)
        token = jwt_token_factory(role="ADMIN")

        mock_segmenter = MagicMock()
        mock_segmenter.is_loaded.return_value = False

        with patch("app.ai.road_segmenter.get_road_segmenter", return_value=mock_segmenter):
            resp = await test_client.post(
                "/api/v1/road/segment/batch",
                json={"dataset_id": ds.dataset_id, "scope": "remaining"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 503
        assert "Road segmentation model not available" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_road_batch_queues_when_model_loaded(self, test_client, db_session, jwt_token_factory):
        from unittest.mock import MagicMock, patch

        ds, _ = await _seed_dataset_with_annotations(db_session, count=3)
        token = jwt_token_factory(role="ADMIN")

        mock_segmenter = MagicMock()
        mock_segmenter.is_loaded.return_value = True

        with (
            patch("app.ai.road_segmenter.get_road_segmenter", return_value=mock_segmenter),
            patch("app.workers.tasks.auto_label_road_task") as mock_task,
        ):
            mock_task.apply_async.return_value = None
            resp = await test_client.post(
                "/api/v1/road/segment/batch",
                json={"dataset_id": ds.dataset_id, "scope": "remaining"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_images"] == 3
        mock_task.apply_async.assert_called_once()


class TestJsonSafeBatchWrites:
    def test_json_safe_converts_numpy_float32(self):
        from app.core.json_utils import json_safe

        payload = {
            "objects": [
                {
                    "label": "car_private",
                    "confidence": np.float32(0.91),
                    "bbox": [
                        np.float32(0.1),
                        np.float64(0.2),
                        np.int64(3),
                        0.4,
                    ],
                    "mask": np.array([[0.0, 0.5], [1.0, 1.0]], dtype=np.float32),
                }
            ]
        }

        sanitized = json_safe(payload)
        json.dumps(sanitized)

        obj = sanitized["objects"][0]
        assert isinstance(obj["confidence"], float)
        assert all(isinstance(v, (int, float)) for v in obj["bbox"])
        assert obj["mask"] == [[0.0, 0.5], [1.0, 1.0]]

    @pytest.mark.asyncio
    async def test_annotation_sanitizes_detected_objects_on_assign(self, db_session):
        ds, annotations = await _seed_dataset_with_annotations(db_session, count=1)
        ann = annotations[0]

        ann.detected_objects = {
            "objects": [
                {
                    "label": "car_private",
                    "confidence": np.float32(0.87),
                    "bbox": [np.float32(0.1), np.float32(0.2), np.float32(0.3), np.float32(0.4)],
                }
            ],
            "_checksum": "",
        }
        ann.auto_labels = {
            "labels": ann.detected_objects["objects"],
            "batch_inferred": True,
        }

        await db_session.flush()
        json.dumps(ann.detected_objects)
        json.dumps(ann.auto_labels)

        assert isinstance(ann.detected_objects["objects"][0]["confidence"], float)

    @pytest.mark.asyncio
    async def test_auto_label_annotations_persists_numpy_detections(self, db_session):
        from app.workers.tasks import _auto_label_annotations_async

        ds, annotations = await _seed_dataset_with_annotations(db_session, count=1)
        ann = annotations[0]

        numpy_detections = [
            {
                "label": "car_private",
                "class_name": "car",
                "confidence": np.float32(0.92),
                "bbox": [
                    np.float32(0.05),
                    np.float32(0.1),
                    np.float32(0.2),
                    np.float32(0.15),
                ],
            }
        ]

        mock_mc = MagicMock()
        mock_mc.get_object.return_value.read.return_value = b"fake-image-bytes"

        with (
            patch("app.core.dependencies.get_minio_client_sync", return_value=mock_mc),
            patch("app.services.prelabel.prelabel_image", return_value=numpy_detections),
            patch("app.core.database.async_session") as mock_session_factory,
        ):
            mock_session_factory.return_value.__aenter__.return_value = db_session
            mock_session_factory.return_value.__aexit__.return_value = None

            summary = await _auto_label_annotations_async([str(ann.id)])

        assert summary["processed"] == 1
        assert summary["failed"] == 0
        await db_session.refresh(ann)
        status = ann.status.value if hasattr(ann.status, "value") else ann.status
        assert status == "AUTO_LABELED"
        json.dumps(ann.detected_objects)
        json.dumps(ann.auto_labels)
        assert isinstance(ann.detected_objects["objects"][0]["confidence"], float)
