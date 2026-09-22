from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.ingestion import IngestionBatch


class FakeResult:
    def __init__(self, class_id, class_name, confidence=0.9, bbox=None):
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox or [0.0, 0.0, 0.5, 0.5]
        self.mask_rle = ""
        self.polygon = None


class TestAgriClasses:
    async def test_get_classes_returns_list(self, test_client: AsyncClient, jwt_token_factory: object):
        token = jwt_token_factory("ADMIN")
        resp = await test_client.get(
            "/api/v1/agri/classes",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "classes" in data
        assert "version" in data
        assert data["version"] == "v1.0"
        assert len(data["classes"]) > 0

    async def test_get_classes_without_auth_returns_200(self, test_client: AsyncClient):
        resp = await test_client.get("/api/v1/agri/classes")
        assert resp.status_code == 200
        data = resp.json()
        assert "classes" in data

    async def test_classes_contain_crop_and_health_entries(self, test_client: AsyncClient, jwt_token_factory: object):
        token = jwt_token_factory("ADMIN")
        resp = await test_client.get(
            "/api/v1/agri/classes",
            headers={"Authorization": f"Bearer {token}"},
        )
        classes = resp.json()["classes"]
        categories = {c["category"] for c in classes}
        assert "crop" in categories
        assert "health" in categories
        names = [c["name"] for c in classes]
        assert "maize" in names
        assert "rice" in names
        assert "healthy" in names
        assert "diseased" in names


class TestAgriSegment:
    async def test_segment_nonexistent_image_returns_404(self, test_client: AsyncClient, jwt_token_factory: object):
        token = jwt_token_factory("ADMIN")
        fake_id = str(uuid4())
        resp = await test_client.post(
            "/api/v1/agri/segment",
            json={"image_id": fake_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_segment_requires_auth(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/v1/agri/segment",
            json={"image_id": str(uuid4())},
        )
        assert resp.status_code in (401, 403)


class TestAgriSegmentBatch:
    async def test_batch_requires_auth(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/v1/agri/segment/batch",
            json={"image_ids": [str(uuid4())]},
        )
        assert resp.status_code in (401, 403)


class TestAgriResult:
    async def test_get_nonexistent_result_returns_404(self, test_client: AsyncClient, jwt_token_factory: object):
        token = jwt_token_factory("ADMIN")
        fake_id = str(uuid4())
        resp = await test_client.get(
            f"/api/v1/agri/result/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_get_result_requires_auth(self, test_client: AsyncClient):
        resp = await test_client.get(f"/api/v1/agri/result/{uuid4()}")
        assert resp.status_code in (401, 403)

    async def test_update_nonexistent_result_returns_404(self, test_client: AsyncClient, jwt_token_factory: object):
        token = jwt_token_factory("ADMIN")
        fake_id = str(uuid4())
        resp = await test_client.patch(
            f"/api/v1/agri/result/{fake_id}",
            json={"crop_type": "maize"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_update_result_requires_role(self, test_client: AsyncClient, jwt_token_factory: object):
        token = jwt_token_factory("BUYER")
        resp = await test_client.patch(
            f"/api/v1/agri/result/{uuid4()}",
            json={"crop_type": "maize"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (401, 403)


class TestAgriAnalyze:
    async def test_analyze_requires_auth(self, test_client: AsyncClient):
        resp = await test_client.post(
            "/api/v1/agri/analyze",
            json={"dataset_id": str(uuid4())},
        )
        assert resp.status_code in (401, 403)

    async def test_analyze_requires_admin_or_qa_role(self, test_client: AsyncClient, jwt_token_factory: object):
        token = jwt_token_factory("ANNOTATOR")
        resp = await test_client.post(
            "/api/v1/agri/analyze",
            json={"dataset_id": str(uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (401, 403)

    async def test_analyze_with_valid_role_returns_report_shape(
        self, test_client: AsyncClient, jwt_token_factory: object
    ):
        token = jwt_token_factory("ADMIN")
        resp = await test_client.post(
            "/api/v1/agri/analyze",
            json={"dataset_id": str(uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "dataset_id" in data
        assert "total_images" in data
        assert "crop_breakdown" in data
        assert "health_breakdown" in data
        assert "health_score" in data
        assert "weed_pressure" in data
        assert "pest_risk" in data
        assert data["total_images"] >= 0
        assert 0.0 <= data["health_score"] <= 1.0
        assert data["weed_pressure"] in ("low", "medium", "high")
        assert data["pest_risk"] in ("low", "medium", "high")

    async def test_analyze_is_scoped_to_dataset(self, db_session, test_client, jwt_token_factory):
        from app.models.agri_annotation import AgriAnnotation
        from app.models.dataset import Dataset
        from app.models.enums import (
            AnnotationStatus,
            BatchStatus,
            DatasetStatus,
            LicenseType,
            NodeCategory,
            NodeStatus,
            PIIMode,
        )
        from app.models.node import Node

        node = Node(
            node_id=f"agri-{uuid4().hex[:8]}",
            district="Lilongwe",
            latitude=-13.96,
            longitude=33.77,
            category=NodeCategory.AGRI,
            hardware_profile={},
            network_config={},
            capture_schedule="daily_1200",
            interest_classes=["crop", "health"],
            pii_mode=PIIMode.NONE,
            firmware_version="1.0.0",
            public_key=b"\x00" * 32,
            status=NodeStatus.ONLINE,
            is_enabled=True,
        )
        db_session.add(node)
        await db_session.flush()

        batch = IngestionBatch(
            batch_id=f"agri-batch-{uuid4().hex[:8]}",
            node_id=node.id,
            hub_id="test-hub",
            event_count=2,
            file_size_bytes=1024,
            checksum_sha256="0" * 64,
            node_signature=b"\x01" * 64,
            compression_codec="none",
            quality_scores={},
            status=BatchStatus.INGESTED,
        )
        db_session.add(batch)
        await db_session.flush()

        datasets = []
        for label in ("ds-a", "ds-b"):
            ds = Dataset(
                dataset_id=f"{label}-{uuid4().hex[:8]}",
                name=f"Dataset {label}",
                version="1.0",
                status=DatasetStatus.READY,
                sample_count=1,
                classes={},
                annotations_per_image=1.0,
                image_width=100,
                image_height=100,
                geographic_coverage={},
                demographic_report={},
                consent_coverage_pct=1.0,
                pii_scrub_verified=True,
                iaa_score=0.0,
                formats=[],
                price_usd=0,
                license_type=LicenseType.ANNUAL,
            )
            db_session.add(ds)
            await db_session.flush()
            datasets.append(ds)

        ann_a = Annotation(
            batch_id=batch.id,
            image_index=0,
            image_path="images/a.jpg",
            thumbnail_path="thumbs/a.jpg",
            detected_objects={},
            auto_labels={},
            status=AnnotationStatus.PENDING,
            quality_score=0.8,
            iaa_score=0.8,
            dataset_id=datasets[0].id,
        )
        ann_b = Annotation(
            batch_id=batch.id,
            image_index=1,
            image_path="images/b.jpg",
            thumbnail_path="thumbs/b.jpg",
            detected_objects={},
            auto_labels={},
            status=AnnotationStatus.PENDING,
            quality_score=0.8,
            iaa_score=0.8,
            dataset_id=datasets[1].id,
        )
        db_session.add_all([ann_a, ann_b])
        await db_session.flush()

        db_session.add_all(
            [
                AgriAnnotation(
                    annotation_id=ann_a.id,
                    crop_type="maize",
                    health_status="healthy",
                    instances=[],
                ),
                AgriAnnotation(
                    annotation_id=ann_b.id,
                    crop_type="rice",
                    health_status="diseased",
                    instances=[],
                ),
            ]
        )
        await db_session.commit()

        token = jwt_token_factory("ADMIN")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await test_client.post(
            "/api/v1/agri/analyze",
            json={"dataset_id": str(datasets[0].id)},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_images"] == 1
        assert data["crop_breakdown"] == {"maize": 1.0}
        assert data["health_breakdown"] == {"healthy": 1.0}


class TestAgriSegmentMergedInstances:
    async def _create_annotation(self, db_session: AsyncSession) -> str:

        from app.models.enums import BatchStatus, NodeCategory, PIIMode
        from app.models.node import Node

        node = Node(
            node_id=f"node-{uuid4().hex[:8]}",
            district="test",
            latitude=-13.0,
            longitude=33.0,
            category=NodeCategory.AGRI,
            hardware_profile={},
            network_config={},
            capture_schedule="daily_1200",
            interest_classes=["crop", "health"],
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

        aid = uuid4()
        annotation = Annotation(
            id=aid,
            batch_id=batch.id,
            image_index=0,
            image_path=f"test/{aid}.jpg",
            thumbnail_path=f"thumb/{aid}.jpg",
            detected_objects={},
            auto_labels={},
            quality_score=0.0,
            status="CERTIFIED",
        )
        db_session.add(annotation)
        await db_session.flush()
        return str(aid)

    async def test_segment_merges_crop_and_health_instances(
        self, test_client: AsyncClient, jwt_token_factory: object, db_session: AsyncSession
    ):
        aid = await self._create_annotation(db_session)

        token = jwt_token_factory("ADMIN")
        fake_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        import io

        from PIL import Image as PILImage

        fake_pil_bytes = io.BytesIO()
        PILImage.fromarray(fake_image).save(fake_pil_bytes, format="JPEG")
        fake_pil_bytes.seek(0)

        crop_instances = [
            FakeResult(0, "maize", 0.91, [0.1, 0.1, 0.3, 0.3]),
            FakeResult(0, "maize", 0.85, [0.5, 0.5, 0.2, 0.2]),
            FakeResult(1, "rice", 0.78, [0.3, 0.3, 0.2, 0.2]),
        ]
        health_instances = [
            FakeResult(0, "healthy", 0.95, [0.15, 0.15, 0.25, 0.25]),
            FakeResult(1, "stressed", 0.72, [0.4, 0.4, 0.15, 0.15]),
        ]

        mock_crop = MagicMock()
        mock_crop.segment.return_value = crop_instances
        mock_health = MagicMock()
        mock_health.segment.return_value = health_instances

        with (
            patch("app.ai.agri_segmenter.get_agri_crop_segmenter", AsyncMock(return_value=mock_crop)),
            patch("app.ai.agri_segmenter.get_agri_health_segmenter", AsyncMock(return_value=mock_health)),
            patch("app.api.agri.get_minio_client") as mock_get_mc,
        ):
            mc = MagicMock()
            mc.get_object.return_value.read.return_value = fake_pil_bytes.getvalue()
            mock_get_mc.return_value = mc

            resp = await test_client.post(
                "/api/v1/agri/segment",
                json={"image_id": aid},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert "instances" in data
        assert len(data["instances"]) == 5

        names = [inst["class_name"] for inst in data["instances"]]
        assert "maize" in names
        assert "rice" in names
        assert "healthy" in names
        assert "stressed" in names

        assert data["crop_type"] == "maize"
        assert data["health_status"] in ("healthy", "stressed")
        assert data["model_version"] == "yolov8n-seg-v1"
        assert "latency_ms" in data

        for inst in data["instances"]:
            assert "class_name" in inst
            assert "class_id" in inst
            assert "confidence" in inst
            assert "bbox" in inst

    async def test_dominant_class_name_by_name_not_id(
        self, test_client: AsyncClient, jwt_token_factory: object, db_session: AsyncSession
    ):
        from app.ai.agri_segmenter import dominant_class_name

        result_a = FakeResult(99, "maize")
        result_b = FakeResult(0, "healthy")
        result_c = FakeResult(1, "healthy")

        result = dominant_class_name([result_a, result_b, result_c], default="unknown")
        assert result == "healthy"

        result2 = dominant_class_name([result_a], default="unknown")
        assert result2 == "maize"

        result3 = dominant_class_name([], default="fallback")
        assert result3 == "fallback"
