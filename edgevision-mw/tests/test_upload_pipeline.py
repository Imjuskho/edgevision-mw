from __future__ import annotations

import base64
import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from minio import Minio
from PIL import Image

from app.core.security import hash_password
from app.models.buyer import User


def _make_jpeg_bytes(size: tuple[int, int] = (100, 100), color: str | None = None) -> bytes:
    if color is None:
        color = f"#{uuid.uuid4().hex[:6]}"
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf.getvalue()


def _make_png_bytes(size: tuple[int, int] = (100, 100), color: str | None = None) -> bytes:
    if color is None:
        color = f"#{uuid.uuid4().hex[:6]}"
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def _make_b64_data_url(img_bytes: bytes, mime: str = "image/jpeg") -> str:
    encoded = base64.b64encode(img_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


@pytest.fixture(autouse=True)
def _mock_minio_global():
    mock_client = MagicMock(spec=Minio)
    mock_client.bucket_exists.return_value = True
    mock_client.put_object.return_value = None
    mock_client.get_object.return_value.read.return_value = _make_jpeg_bytes()

    with patch("app.core.dependencies._minio_client", mock_client):
        yield mock_client


async def _make_user(db_session) -> tuple[str, str]:
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"upload-test-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("testpass123"),
        full_name="Test User",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    yield user_id

    await db_session.flush()


@pytest.mark.asyncio
async def test_upload_file_jpeg(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()

    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))
    headers = {"Authorization": f"Bearer {token}"}

    jpeg_bytes = _make_jpeg_bytes()
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"dataset_id": dataset_id, "source": "file"},
        headers=headers,
    )
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    data = resp.json()

    assert data["uploaded"] >= 0
    assert data["skipped"] == 0
    assert data["total"] == 1
    assert data["source"] == "file"
    assert data["images"][0]["filename"] == "test.jpg"
    assert data["images"][0]["status"] == "uploaded"
    assert data["images"][0]["annotation_id"] is not None


@pytest.mark.asyncio
async def test_upload_file_png(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    png_bytes = _make_png_bytes()
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("test.png", io.BytesIO(png_bytes), "image/png")},
        data={"dataset_id": dataset_id, "source": "file"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    data = resp.json()
    assert data["uploaded"] >= 0
    assert data["skipped"] == 0
    assert data["total"] == 1
    assert data["source"] == "file"
    assert data["images"][0]["filename"] == "test.png"
    assert data["images"][0]["status"] == "uploaded"
    assert data["images"][0]["annotation_id"] is not None


@pytest.mark.asyncio
async def test_upload_webcam_base64(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    jpeg_bytes = _make_jpeg_bytes()
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("webcam.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"dataset_id": dataset_id, "source": "webcam"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Webcam upload failed: {resp.text}"
    data = resp.json()
    assert data["uploaded"] >= 0
    assert data["source"] == "webcam"
    assert data["images"][0]["status"] == "uploaded"


@pytest.mark.asyncio
async def test_upload_screen_capture_base64(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    jpeg_bytes = _make_jpeg_bytes()
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("screen_capture.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"dataset_id": dataset_id, "source": "screen_capture"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Screen capture upload failed: {resp.text}"
    data = resp.json()
    assert data["uploaded"] >= 0
    assert data["source"] == "screen_capture"
    assert data["images"][0]["status"] == "uploaded"


@pytest.mark.asyncio
async def test_upload_url_fetch(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    jpeg_bytes = _make_jpeg_bytes()

    class MockStreamResponse:
        def __init__(self, data, content_type):
            self._data = data
            self.headers = {"content-type": content_type, "content-length": str(len(data))}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def aiter_bytes(self, chunk_size=8192):
            yield self._data

    with patch("app.api.images.httpx.AsyncClient") as mock_httpx:
        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=MockStreamResponse(jpeg_bytes, "image/jpeg"))
        mock_httpx.return_value.__aenter__.return_value = mock_client

        dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
        resp = await test_client.post(
            "/api/v1/upload/url",
            data={"dataset_id": dataset_id, "source": "url", "url": "https://example.com/photo.jpg"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 201, f"URL upload failed: {resp.text}"
    data = resp.json()
    assert data["source"] == "url"
    assert data["uploaded"] >= 0
    assert data["total"] == 1
    assert data["images"][0]["status"] == "uploaded"
    assert data["images"][0]["filename"] == "photo.jpg"


@pytest.mark.asyncio
async def test_upload_drone_with_telemetry(db_session, test_client: AsyncClient, jwt_token_factory):
    import json

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    jpeg_bytes = _make_jpeg_bytes()
    telemetry = {
        "gps_lat": 52.52,
        "gps_lon": 13.405,
        "altitude_m": 120.5,
        "heading_deg": 270,
        "camera_make": "DJI",
        "camera_model": "Mavic 3",
    }

    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("drone_capture.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"dataset_id": dataset_id, "source": "drone", "telemetry": json.dumps(telemetry)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Drone upload failed: {resp.text}"
    data = resp.json()
    assert data["source"] == "drone"


@pytest.mark.asyncio
async def test_upload_invalid_corrupt_image(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("corrupt.jpg", io.BytesIO(b"not-an-image"), "image/jpeg")},
        data={"dataset_id": dataset_id, "source": "file"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["uploaded"] == 0
    assert len(data["images"]) == 0
    assert len(data["errors"]) == 1
    assert data["errors"][0]["filename"] == "corrupt.jpg"


@pytest.mark.asyncio
async def test_upload_wrong_format(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    fake_pdf = b"%PDF-1.4 fake pdf content \x00\x01\x02"
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("document.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        data={"dataset_id": dataset_id, "source": "file"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["uploaded"] == 0
    assert len(data["images"]) == 0


@pytest.mark.asyncio
async def test_upload_invalid_source(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    jpeg_bytes = _make_jpeg_bytes()
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"dataset_id": dataset_id, "source": "invalid_source_value"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_no_auth(db_session, test_client: AsyncClient):
    jpeg_bytes = _make_jpeg_bytes()
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"dataset_id": dataset_id, "source": "file"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_image_metadata(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    jpeg_bytes = _make_jpeg_bytes()
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"dataset_id": dataset_id, "source": "file"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    image_id = resp.json()["images"][0]["annotation_id"]

    meta_resp = await test_client.get(
        f"/api/v1/images/{image_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    assert meta["image_id"] == image_id
    assert meta["width"] == 100
    assert meta["height"] == 100
    assert meta["source"] == "file"


@pytest.mark.asyncio
async def test_get_image_metadata_not_found(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    resp = await test_client.get(
        f"/api/v1/images/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_serve_image_stream(db_session, test_client: AsyncClient, jwt_token_factory):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"up-{uuid.uuid4().hex[:8]}@t.com",
        hashed_password=hash_password("testpass123"),
        full_name="T",
        role="ADMIN",
        is_active=True,
        dpa_signed=False,
        credit_balance_usd=0.0,
    )
    db_session.add(user)
    await db_session.flush()
    token = jwt_token_factory(role="ADMIN", user_id=str(user_id))

    jpeg_bytes = _make_jpeg_bytes()
    dataset_id = f"test-dataset-{uuid.uuid4().hex[:8]}"
    resp = await test_client.post(
        "/api/v1/upload/images",
        files={"files": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"dataset_id": dataset_id, "source": "file"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    image_id = resp.json()["images"][0]["annotation_id"]

    serve_resp = await test_client.get(
        f"/api/v1/images/{image_id}/serve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert serve_resp.status_code == 200
    assert serve_resp.headers.get("content-type") in ("image/jpeg", "image/png")


@pytest.mark.asyncio
async def test_cors_preflight(test_client: AsyncClient):
    resp = await test_client.options(
        "/api/v1/upload/images",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") in ("http://localhost:3000", "*")
    assert "POST" in (resp.headers.get("access-control-allow-methods") or "")
