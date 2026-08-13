"""Tests for video upload frame extraction."""

from __future__ import annotations

import contextlib
import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from minio import Minio
from PIL import Image

from app.core.security import hash_password
from app.models.buyer import User
from app.models.dataset import Dataset
from app.models.enums import DatasetStatus


def _make_jpeg_bytes(size: tuple[int, int] = (64, 48), color: str = "#336699") -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf.getvalue()


def _make_test_mp4(num_frames: int = 3, fps: float = 2.0) -> bytes:
    cv2 = pytest.importorskip("cv2")
    import os
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(tmp.name, fourcc, fps, (64, 48))
        if not writer.isOpened():
            pytest.skip("OpenCV VideoWriter unavailable in this environment")
        for i in range(num_frames):
            import numpy as np

            color = (40 + i * 20, 80, 120)
            frame = np.full((48, 64, 3), color, dtype=np.uint8)
            writer.write(frame)
        writer.release()

        with open(tmp.name, "rb") as f:
            return f.read()
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp.name)


@pytest.fixture(autouse=True)
def _mock_minio_global():
    mock_client = MagicMock(spec=Minio)
    mock_client.bucket_exists.return_value = True
    mock_client.put_object.return_value = None
    mock_client.get_object.return_value.read.return_value = _make_jpeg_bytes()

    with patch("app.core.dependencies._minio_client", mock_client):
        with patch("app.core.config.settings.AUTO_PRELABEL_ON_UPLOAD", False):
            yield mock_client


@pytest.mark.asyncio
async def test_upload_video_extracts_frames(db_session, test_client: AsyncClient, jwt_token_factory):
    pytest.importorskip("cv2")

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"video-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("testpass123"),
        full_name="Video Tester",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    ds = Dataset(
        dataset_id=f"video-ds-{uuid.uuid4().hex[:8]}",
        name="Video Dataset",
        version="1.0",
        status=DatasetStatus.BUILDING,
        sample_count=0,
        classes={},
        annotations_per_image=0.0,
        image_width=0,
        image_height=0,
        geographic_coverage={"districts": []},
        demographic_report={"age_groups": {}},
        consent_coverage_pct=0.0,
        pii_scrub_verified=False,
        iaa_score=0.0,
        formats=[],
        price_usd=0,
        license_type="ANNUAL",
    )
    db_session.add(ds)
    await db_session.flush()

    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))
    headers = {"Authorization": f"Bearer {token}"}

    video_bytes = _make_test_mp4(num_frames=4, fps=2.0)
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("iphone_clip.mov", io.BytesIO(video_bytes), "video/quicktime")},
        data={"dataset_id": ds.dataset_id, "source": "file"},
        headers=headers,
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["uploaded"] >= 1, data
    assert data["total"] == 1
    assert any(entry["status"] == "uploaded" for entry in data["images"])
    assert all("#frame_" in entry["filename"] for entry in data["images"])


@pytest.mark.asyncio
async def test_upload_video_all_frames_listed(db_session, test_client: AsyncClient, jwt_token_factory):
    """Every extracted frame must appear in studio image list (not collapsed by checksum dedup)."""
    pytest.importorskip("cv2")
    from sqlalchemy import func, select

    from app.models.annotation import Annotation
    from app.models.image import ImageRecord

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"video-all-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("testpass123"),
        full_name="Video All Frames",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    ds = Dataset(
        dataset_id=f"video-all-{uuid.uuid4().hex[:8]}",
        name="Video All Frames Dataset",
        version="1.0",
        status=DatasetStatus.BUILDING,
        sample_count=0,
        classes={},
        annotations_per_image=0.0,
        image_width=0,
        image_height=0,
        geographic_coverage={"districts": []},
        demographic_report={"age_groups": {}},
        consent_coverage_pct=0.0,
        pii_scrub_verified=False,
        iaa_score=0.0,
        formats=[],
        price_usd=0,
        license_type="ANNUAL",
    )
    db_session.add(ds)
    await db_session.flush()

    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))
    headers = {"Authorization": f"Bearer {token}"}

    video_bytes = _make_test_mp4(num_frames=4, fps=2.0)
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("iphone_clip.mov", io.BytesIO(video_bytes), "video/quicktime")},
        data={"dataset_id": ds.dataset_id, "source": "file"},
        headers=headers,
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    uploaded_count = data["uploaded"]
    assert uploaded_count >= 2, data

    image_count = (
        await db_session.execute(
            select(func.count()).select_from(ImageRecord).where(ImageRecord.dataset_id == ds.id)
        )
    ).scalar()
    ann_count = (
        await db_session.execute(select(func.count()).where(Annotation.dataset_id == ds.id))
    ).scalar()

    assert image_count == uploaded_count
    assert ann_count == uploaded_count

    list_resp = await test_client.get(
        f"/api/v1/studio/datasets/{ds.dataset_id}/images?page=1&page_size=50",
        headers=headers,
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert listed["total"] == uploaded_count
    assert len(listed["images"]) == uploaded_count


@pytest.mark.asyncio
async def test_upload_video_identical_frame_bytes_all_saved(db_session, test_client: AsyncClient, jwt_token_factory):
    """Identical JPEG bytes at different frame indices must not collapse to one image."""
    from unittest.mock import patch

    from app.services.video_processing import ExtractedFrame, VideoProbe

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"video-dup-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("testpass123"),
        full_name="Video Dedup",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    ds = Dataset(
        dataset_id=f"video-dup-{uuid.uuid4().hex[:8]}",
        name="Video Dedup Dataset",
        version="1.0",
        status=DatasetStatus.BUILDING,
        sample_count=0,
        classes={},
        annotations_per_image=0.0,
        image_width=0,
        image_height=0,
        geographic_coverage={"districts": []},
        demographic_report={"age_groups": {}},
        consent_coverage_pct=0.0,
        pii_scrub_verified=False,
        iaa_score=0.0,
        formats=[],
        price_usd=0,
        license_type="ANNUAL",
    )
    db_session.add(ds)
    await db_session.flush()

    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))
    headers = {"Authorization": f"Bearer {token}"}

    identical_jpeg = _make_jpeg_bytes()
    fake_frames = [
        ExtractedFrame(index=i, timestamp_sec=float(i), jpeg_bytes=identical_jpeg, width=64, height=48)
        for i in range(3)
    ]
    fake_probe = VideoProbe(
        filename="clip.mov",
        width=64,
        height=48,
        fps=1.0,
        frame_count=3,
        duration_sec=3.0,
        codec="hvc1",
        has_depth_track=False,
        device_make="Apple",
        device_model="iPhone",
        notes=[],
    )

    with patch("app.api.images.extract_video_frames", return_value=(fake_probe, fake_frames)):
        resp = await test_client.post(
            "/api/v1/upload/images",
            files={"files": ("clip.mov", io.BytesIO(b"fake-video"), "video/quicktime")},
            data={"dataset_id": ds.dataset_id, "source": "file"},
            headers=headers,
        )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["uploaded"] == 3, data
    assert len(data["images"]) == 3

    list_resp = await test_client.get(
        f"/api/v1/studio/datasets/{ds.dataset_id}/images?page=1&page_size=50",
        headers=headers,
    )
    listed = list_resp.json()
    assert listed["total"] == 3
    assert len(listed["images"]) == 3


@pytest.mark.asyncio
async def test_upload_invalid_video_returns_error(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"bad-video-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("testpass123"),
        full_name="Bad Video",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()

    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))
    headers = {"Authorization": f"Bearer {token}"}

    fake_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("video.mp4", io.BytesIO(fake_mp4), "video/mp4")},
        data={"dataset_id": dataset_id, "source": "file"},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["uploaded"] == 0
    assert len(body["errors"]) == 1
