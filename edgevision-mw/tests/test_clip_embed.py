"""Tests for Phase 8.3 — CLIP embedding service."""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image


def _make_test_image(width: int = 224, height: int = 224) -> bytes:
    img = Image.new("RGB", (width, height), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_mock_clip_session():
    embedding = np.random.randn(512).astype(np.float32)
    embedding = embedding / np.linalg.norm(embedding)

    session = MagicMock()
    input_info = MagicMock()
    input_info.name = "input_ids"
    session.get_inputs.return_value = [input_info]
    session.run.return_value = [embedding[np.newaxis, ...]]
    return session, embedding


class TestClipEmbedService:
    def test_compute_clip_embedding_returns_vector(self):
        from app.services.clip_embed import compute_clip_embedding

        img_bytes = _make_test_image()
        mock_session, expected_emb = _make_mock_clip_session()

        with (
            patch("app.services.clip_embed._find_clip_model", return_value=MagicMock(exists=lambda: True)),
            patch("onnxruntime.InferenceSession", return_value=mock_session),
        ):
            result = compute_clip_embedding(img_bytes)

            assert result is not None
            assert len(result) == 512
            assert all(isinstance(v, float) for v in result)

    def test_compute_clip_embedding_returns_none_on_no_model(self):
        from app.services.clip_embed import compute_clip_embedding

        with patch("app.services.clip_embed._find_clip_model", return_value=None):
            result = compute_clip_embedding(b"fake")
            assert result is None

    def test_compute_clip_embedding_returns_none_on_corrupt_image(self):
        from app.services.clip_embed import compute_clip_embedding

        with patch("app.services.clip_embed._find_clip_model", return_value=MagicMock(exists=lambda: True)):
            result = compute_clip_embedding(b"not_an_image")
            assert result is None

    def test_compute_clip_embedding_normalizes_output(self):
        from app.services.clip_embed import compute_clip_embedding

        img_bytes = _make_test_image()
        mock_session, _ = _make_mock_clip_session()

        with (
            patch("app.services.clip_embed._find_clip_model", return_value=MagicMock(exists=lambda: True)),
            patch("onnxruntime.InferenceSession", return_value=mock_session),
        ):
            result = compute_clip_embedding(img_bytes)

            assert result is not None
            norm = np.linalg.norm(result)
            assert abs(norm - 1.0) < 0.01


class TestClipEmbedAPI:
    @pytest.mark.asyncio
    async def test_embed_requires_auth(self, test_client):
        resp = await test_client.post(
            "/api/v1/studio/clip/embed",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_embed_rejects_non_image(self, test_client, jwt_token_factory):
        token = jwt_token_factory(role="ADMIN")
        resp = await test_client.post(
            "/api/v1/studio/clip/embed",
            files={"file": ("test.txt", b"text", "text/plain")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_embed_returns_embedding_info(self, test_client, jwt_token_factory):
        token = jwt_token_factory(role="ADMIN")
        img_bytes = _make_test_image()
        mock_session, _ = _make_mock_clip_session()

        with (
            patch("app.services.clip_embed._find_clip_model", return_value=MagicMock(exists=lambda: True)),
            patch("onnxruntime.InferenceSession", return_value=mock_session),
        ):
            resp = await test_client.post(
                "/api/v1/studio/clip/embed",
                files={"file": ("test.jpg", img_bytes, "image/jpeg")},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["embedding_dim"] == 512
            assert "stored" in data
