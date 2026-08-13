"""CLIP embedding API endpoint.

Provides server-side CLIP embedding computation for semantic deduplication.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import Annotation, ImageEmbedding
from app.services.clip_embed import compute_clip_embedding

clip_router = APIRouter(prefix="/studio/clip", tags=["clip"])


class EmbedRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_id: str


class EmbedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_id: str
    embedding_dim: int
    stored: bool


class SimilarityRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    image_a_id: str
    image_b_id: str


class SimilarityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    image_a_id: str
    image_b_id: str
    similarity: float
    method: str


@clip_router.post("/embed", response_model=EmbedResponse)
async def embed_image(
    file: UploadFile = File(...),
    annotation_id: str = "",
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute CLIP embedding for an uploaded image and optionally store it."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 20MB")

    embedding = compute_clip_embedding(contents)
    if embedding is None:
        raise HTTPException(status_code=500, detail="CLIP embedding computation failed")

    stored = False
    if annotation_id:
        try:
            ann_uuid = UUID(annotation_id)
            result = await db.execute(
                select(Annotation).where(Annotation.id == ann_uuid)
            )
            ann = result.scalar_one_or_none()
            if ann:
                emb = ImageEmbedding(
                    image_path=ann.image_path or "",
                    annotation_id=ann_uuid,
                    model_name="clip-vit-b32",
                    embedding=embedding,
                    metadata_json={"source": "api_embed"},
                )
                db.add(emb)
                await db.commit()
                stored = True
        except Exception:
            await db.rollback()

    return EmbedResponse(
        annotation_id=annotation_id or "unstored",
        embedding_dim=len(embedding),
        stored=stored,
    )


@clip_router.post("/similarity", response_model=SimilarityResponse)
async def compute_similarity(
    body: SimilarityRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute cosine similarity between two stored CLIP embeddings."""
    import numpy as np

    result_a = await db.execute(
        select(ImageEmbedding).where(ImageEmbedding.annotation_id == UUID(body.image_a_id))
    )
    emb_a = result_a.scalar_one_or_none()

    result_b = await db.execute(
        select(ImageEmbedding).where(ImageEmbedding.annotation_id == UUID(body.image_b_id))
    )
    emb_b = result_b.scalar_one_or_none()

    if emb_a is None or emb_b is None:
        raise HTTPException(status_code=404, detail="Embedding not found for one or both images")

    if emb_a.embedding is None or emb_b.embedding is None:
        raise HTTPException(status_code=400, detail="Embedding data is null")

    vec_a = np.array(emb_a.embedding, dtype=np.float32)
    vec_b = np.array(emb_b.embedding, dtype=np.float32)

    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a > 0:
        vec_a = vec_a / norm_a
    if norm_b > 0:
        vec_b = vec_b / norm_b

    similarity = float(np.dot(vec_a, vec_b))

    return SimilarityResponse(
        image_a_id=body.image_a_id,
        image_b_id=body.image_b_id,
        similarity=round(similarity, 6),
        method="clip_cosine",
    )
