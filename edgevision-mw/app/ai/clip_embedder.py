from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from app.core.logging import get_logger

logger = get_logger("edgevision.clip_embedder")

CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)


def _find_model() -> Path | None:
    candidates = [
        Path("frontend/public/models/clip_vit_b32.onnx"),
        Path("/code/frontend/public/models/clip_vit_b32.onnx"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


class CLIPEmbedder:
    def __init__(self, model_path: str | None = None):
        self._model_path = model_path or _find_model()
        self._session = None
        if self._model_path:
            self._load()

    def _load(self) -> None:
        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(
                str(self._model_path),
                providers=["CPUExecutionProvider"],
            )
            logger.info("clip_embedder_loaded", path=str(self._model_path))
        except Exception as exc:
            logger.warning("clip_embedder_load_failed", error=str(exc))

    def embed(self, image_or_text: object) -> list[float]:
        if self._session is None:
            return [0.0] * 512
        try:
            if isinstance(image_or_text, bytes):
                img = Image.open(__import__("io").BytesIO(image_or_text)).convert("RGB")
            elif isinstance(image_or_text, Image.Image):
                img = image_or_text.convert("RGB")
            elif isinstance(image_or_text, np.ndarray):
                img = Image.fromarray(image_or_text).convert("RGB")
            else:
                return [0.0] * 512
            resized = img.resize((224, 224), Image.BILINEAR)
            arr = np.array(resized, dtype=np.float32) / 255.0
            arr = (arr - CLIP_MEAN) / CLIP_STD
            arr = arr.transpose(2, 0, 1)[np.newaxis, ...]
            outputs = self._session.run(None, {self._session.get_inputs()[0].name: arr})
            embedding = outputs[0].flatten()
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            return embedding.tolist()
        except Exception as exc:
            logger.warning("clip_embed_failed", error=str(exc))
            return [0.0] * 512

    def is_loaded(self) -> bool:
        return self._session is not None
