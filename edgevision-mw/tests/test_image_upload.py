from __future__ import annotations

import io
import random
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image


@pytest.mark.asyncio
async def test_image_upload_no_leading_slash(
    db_session, test_client: AsyncClient, jwt_token_factory
):
    reg = await test_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"upload-test-{uuid.uuid4().hex[:8]}@test.com",
            "password": "securepass123",
            "full_name": "Upload Tester",
        },
    )
    assert reg.status_code == 201
    user_id = reg.json()["id"]

    token = jwt_token_factory(role="ADMIN", user_id=user_id)
    headers = {"Authorization": f"Bearer {token}"}

    img = Image.new(
        "RGB", (100, 100),
        color=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)),
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    with patch("app.services.images.put_object", new=AsyncMock()) as mock_put:
        upload_resp = await test_client.post(
            "/api/v1/upload/images",
            files={"files": ("test_image.png", buf, "image/png")},
            data={"dataset_id": dataset_id},
            headers=headers,
        )
    assert upload_resp.status_code == 201, f"Upload failed: {upload_resp.text}"
    data = upload_resp.json()

    assert data["dataset_id"] == dataset_id
    assert data["uploaded"] > 0
    assert data["total"] == 1

    image_info = data["images"][0]
    assert image_info["status"] == "uploaded"
    assert image_info["filename"] == "test_image.png"

    call_kwargs = mock_put.call_args_list
    assert len(call_kwargs) >= 1
    object_key = call_kwargs[0][0][1]
    assert not object_key.startswith("/"), f"MinIO key has leading slash: {object_key}"


@pytest.mark.asyncio
async def test_image_serve_no_leading_slash(
    db_session, test_client: AsyncClient, jwt_token_factory, mock_minio
):
    mock_minio.get_object.return_value.read.return_value = b"fake-image-data"

    from app.models.annotation import Annotation
    from app.models.dataset import Dataset
    from app.models.enums import DatasetStatus
    from app.models.ingestion import IngestionBatch
    from app.models.node import Node

    ds_id = f"ds{uuid.uuid4().hex[:8]}"
    ds = Dataset(
        dataset_id=ds_id,
        name="Serve Test Dataset",
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
        iaa_score=0.0,
        formats=[],
        price_usd=0,
        license_type="ANNUAL",
    )
    db_session.add(ds)
    await db_session.flush()

    node = Node(
        node_id=f"n{uuid.uuid4().hex[:10]}",
        district="Lilongwe",
        latitude=-13.9626,
        longitude=33.7741,
        category="ROAD",
        hardware_profile={},
        network_config={},
        capture_schedule="manual",
        interest_classes=[],
        pii_mode="NONE",
        firmware_version="1.0",
        public_key=b"\x00" * 32,
        status="ONLINE",
        is_enabled=True,
    )
    db_session.add(node)
    await db_session.flush()

    batch = IngestionBatch(
        batch_id=f"b{uuid.uuid4().hex[:20]}",
        node_id=node.id,
        hub_id=f"h{uuid.uuid4().hex[:10]}",
        event_count=1,
        file_size_bytes=100,
        checksum_sha256="abc123",
        node_signature=b"\x00",
        compression_codec="none",
        status="INGESTED",
        quality_scores={},
    )
    db_session.add(batch)
    await db_session.flush()

    image_path = f"datasets/{ds_id}/images/test.jpg"
    ann = Annotation(
        batch_id=batch.id,
        image_index=0,
        image_path=image_path,
        thumbnail_path=f"datasets/{ds_id}/thumbnails/test.jpg",
        detected_objects={},
        auto_labels={},
        status="PENDING",
        quality_score=0.9,
        iaa_score=0.9,
    )
    db_session.add(ann)
    await db_session.commit()

    token = jwt_token_factory()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.core.dependencies.get_minio_client", return_value=mock_minio):
        serve_resp = await test_client.get(
            f"/api/v1/studio/images/{ann.id}/serve",
            headers=headers,
        )
    assert serve_resp.status_code == 200

    call_kwargs = mock_minio.get_object.call_args
    assert call_kwargs is not None
    object_key = call_kwargs[0][1]
    assert object_key == image_path, f"Expected {image_path}, got {object_key}"
    assert not object_key.startswith("/"), f"MinIO key has leading slash: {object_key}"
