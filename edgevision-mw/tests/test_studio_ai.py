import base64
import hashlib
import io
from unittest.mock import patch
from uuid import uuid4

import pytest
from PIL import Image

from app.core.security import create_access_token
from app.models.buyer import User
from app.models.image import ImageRecord


async def _create_user(db, role="ANNOTATOR"):
    user_id = uuid4()
    user = User(
        id=user_id,
        email=f"{user_id.hex[:8]}@test.com",
        hashed_password="fakehash",
        full_name="Test User",
        role=role,
        is_active=True,
        dpa_signed=True,
    )
    db.add(user)
    await db.commit()
    return user


def _make_test_image_base64() -> str:
    """Create a tiny valid JPEG as base64 for testing."""
    from PIL import Image

    img = Image.new("RGB", (64, 64), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


@pytest.mark.asyncio
async def test_ai_assist_returns_fallback_when_models_unavailable(test_client, db_session):
    user = await _create_user(db_session)
    token = create_access_token({"sub": str(user.id), "role": user.role, "email": user.email})

    resp = await test_client.post(
        "/api/v1/studio/label/ai-assist",
        json={
            "prompt_type": "full_image",
            "image_data": _make_test_image_base64(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "annotations" in data
    assert "inference_time_ms" in data
    assert "model_used" in data
    assert "fallback" in data


@pytest.mark.asyncio
async def test_ai_assist_rejects_missing_image(test_client, db_session):
    user = await _create_user(db_session)
    token = create_access_token({"sub": str(user.id), "role": user.role, "email": user.email})

    resp = await test_client.post(
        "/api/v1/studio/label/ai-assist",
        json={"prompt_type": "full_image"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 400
    assert "image_id or image_data" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ai_assist_rejects_invalid_base64(test_client, db_session):
    user = await _create_user(db_session)
    token = create_access_token({"sub": str(user.id), "role": user.role, "email": user.email})

    resp = await test_client.post(
        "/api/v1/studio/label/ai-assist",
        json={
            "prompt_type": "full_image",
            "image_data": "not-valid-base64!!!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 400
    assert "Invalid image_data" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ai_assist_with_uploaded_image_id(test_client, db_session, mock_minio, jwt_token_factory):
    user = await _create_user(db_session)
    token = create_access_token({"sub": str(user.id), "role": user.role, "email": user.email})

    img = Image.new("RGB", (64, 64), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    record = ImageRecord(
        id=uuid4(),
        storage_key="test/edgevision/image.jpg",
        thumbnail_key="test/edgevision/thumb.jpg",
        filename="image.jpg",
        content_type="image/jpeg",
        size_bytes=len(img_bytes),
        width=64,
        height=64,
        source="file",
        dataset_id=None,
        uploaded_by=user.id,
        tenant_id=None,
        checksum_sha256=hashlib.sha256(img_bytes).hexdigest(),
    )
    db_session.add(record)
    await db_session.commit()

    mock_minio.get_object.return_value.read.return_value = img_bytes

    with patch("app.core.dependencies._minio_client", mock_minio):
        resp = await test_client.post(
            "/api/v1/studio/label/ai-assist",
            json={
                "prompt_type": "full_image",
                "image_id": str(record.id),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data.get("annotations"), list)
    assert mock_minio.get_object.call_args is not None
    assert mock_minio.get_object.call_args[0][1] == record.storage_key


@pytest.mark.asyncio
async def test_ai_assist_batch_returns_list(test_client, db_session):
    user = await _create_user(db_session)
    token = create_access_token({"sub": str(user.id), "role": user.role, "email": user.email})

    img_data = _make_test_image_base64()
    resp = await test_client.post(
        "/api/v1/studio/label/ai-assist/batch",
        json=[
            {"prompt_type": "full_image", "image_data": img_data},
            {"prompt_type": "full_image", "image_data": img_data},
        ],
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    for item in data:
        assert "annotations" in item
        assert "inference_time_ms" in item
