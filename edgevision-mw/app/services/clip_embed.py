"""Server-side CLIP embedding service using ONNX Runtime.

Generates CLIP ViT-B/32 image embeddings for semantic deduplication.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# CLIP preprocessing (standard normalization)
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
CLIP_EMBEDDING_DIM = 512


def _find_clip_model() -> Path | None:
    """Locate the CLIP ONNX model.

    Resolution order:
      1. ``CLIP_VIT_B32_PATH`` environment variable
      2. Project-local ``frontend/public/models/clip_vit_b32.onnx``
    """
    from app.core.config import settings

    candidates = []
    if settings.CLIP_VIT_B32_PATH:
        candidates.append(Path(settings.CLIP_VIT_B32_PATH))
    candidates.append(Path(__file__).resolve().parents[2] / "frontend/public/models/clip_vit_b32.onnx")
    for p in candidates:
        if p.exists():
            return p
    return None


def _preprocess_image(img: Image.Image, size: int = 224) -> np.ndarray:
    """Resize + normalize image for CLIP input."""
    resized = img.resize((size, size), Image.BILINEAR)
    arr = np.array(resized, dtype=np.float32) / 255.0
    arr = (arr - CLIP_MEAN) / CLIP_STD
    arr = arr.transpose(2, 0, 1)  # HWC → CHW
    return arr[np.newaxis, ...]  # batch dim


def compute_clip_embedding(image_bytes: bytes) -> list[float] | None:
    """Compute a CLIP embedding for a single image.

    Returns a 512-dim float list, or None on failure.
    """
    import onnxruntime as ort

    model_path = _find_clip_model()
    if model_path is None:
        logger.warning("CLIP model not found; skipping embedding computation")
        return None

    try:
        img = Image.open(__import__("io").BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        logger.error("Failed to decode image for CLIP embedding: %s", exc)
        return None

    try:
        session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        input_name = session.get_inputs()[0].name
    except Exception as exc:
        logger.error("Failed to load CLIP ONNX model: %s", exc)
        return None

    try:
        tensor = _preprocess_image(img)
        outputs = session.run(None, {input_name: tensor})
        embedding = outputs[0].flatten()

        # L2 normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding.tolist()
    except Exception as exc:
        logger.error("CLIP inference failed: %s", exc)
        return None


async def compute_clip_embeddings_batch(
    image_bytes_list: list[bytes],
) -> list[list[float] | None]:
    """Compute CLIP embeddings for a batch of images."""
    return [compute_clip_embedding(img_bytes) for img_bytes in image_bytes_list]
