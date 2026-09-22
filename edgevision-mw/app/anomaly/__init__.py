"""F4 Open-Set Anomaly Detection Package.

Provides self-supervised per-camera scene embedding, GMM-based outlier scoring,
and feature-driven natural-language anomaly description.

Architecture
------------
    scene_embedder  ->  scorer  ->  describe
    (per-camera          (GMM-based      (template + feature
     autoencoder)         open-set        driven NL)

All models are trained in-memory per-camera and guarded by a minimum
data-volume threshold to prevent false positives on fresh cameras.

Usage
-----
::

    from app.anomaly.scene_embedder import SceneEmbedder
    from app.anomaly.scorer import AnomalyScorer
    from app.anomaly.describe import AnomalyDescriber

    embedder  = SceneEmbedder()
    scorer    = AnomalyScorer()
    describer = AnomalyDescriber()

    # Per-frame pipeline
    embedding = embedder.encode(camera_id, frame_bytes)
    result    = scorer.score(camera_id, embedding)
    if result is not None:
        description = describer.describe(camera_id, result)
"""

from __future__ import annotations

import logging
from typing import Any

from app.anomaly.describe import AnomalyDescriber, build_vlm_prompt
from app.anomaly.scene_embedder import SceneEmbedder
from app.anomaly.scorer import AnomalyScorer

logger = logging.getLogger(__name__)

__all__ = [
    "SceneEmbedder",
    "AnomalyScorer",
    "AnomalyDescriber",
    "build_vlm_prompt",
    "wire_anomaly_to_labeling_queue",
    "get_anomaly_sourced_annotations",
    "get_scene_embedder",
    "get_anomaly_scorer",
    "get_anomaly_describer",
    "run_anomaly_pipeline",
]


# ---------------------------------------------------------------------------
# Global singleton instances (in-process, not shared across workers)
# ---------------------------------------------------------------------------

_scene_embedder: SceneEmbedder | None = None
_anomaly_scorer: AnomalyScorer | None = None
_anomaly_describer: AnomalyDescriber | None = None


def get_scene_embedder() -> SceneEmbedder:
    """Return the process-wide SceneEmbedder singleton."""
    global _scene_embedder
    if _scene_embedder is None:
        _scene_embedder = SceneEmbedder()
    return _scene_embedder


def get_anomaly_scorer() -> AnomalyScorer:
    """Return the process-wide AnomalyScorer singleton."""
    global _anomaly_scorer
    if _anomaly_scorer is None:
        _anomaly_scorer = AnomalyScorer()
    return _anomaly_scorer


def get_anomaly_describer() -> AnomalyDescriber:
    """Return the process-wide AnomalyDescriber singleton."""
    global _anomaly_describer
    if _anomaly_describer is None:
        _anomaly_describer = AnomalyDescriber()
    return _anomaly_describer


# ---------------------------------------------------------------------------
# QA / Labeling Queue Wiring  (lazy-imported to avoid SQLAlchemy at import time)
# ---------------------------------------------------------------------------

async def wire_anomaly_to_labeling_queue(
    db: Any,
    anomaly_event: Any,
    batch_id: Any,
    image_index: int = 0,
    image_path: str = "",
    thumbnail_path: str = "",
) -> Any | None:
    """Create an Annotation record for a flagged anomaly.

    This wires anomaly detections into the existing QA/labeling queue as a
    **distinct source type** (``source: "anomaly_detection"``) carried in the
    ``auto_labels`` JSONB field.  Annotators and QA reviewers can filter the
    queue by this source.

    Parameters
    ----------
    db
        Async database session (:class:`sqlalchemy.ext.asyncio.AsyncSession`).
    anomaly_event
        The persisted :class:`~app.models.frontier_capabilities.AnomalyEvent`
        to wire into the queue.
    batch_id
        FK to the ``ingestion_batches`` table.  Pass the batch that
        produced the frame which triggered the anomaly, or a dedicated
        anomaly-review batch.
    image_index
        Frame index within the batch.
    image_path
        Path to the source frame in object storage.
    thumbnail_path
        Path to a thumbnail for fast UI rendering.

    Returns
    -------
    Annotation | None
        The newly created annotation, or ``None`` if a duplicate already
        exists for this anomaly event.
    """
    from uuid import uuid4

    from sqlalchemy import select

    from app.models.annotation import Annotation
    from app.models.enums import AnnotationStatus

    # Guard: check for existing annotation to avoid duplicates
    existing = await db.execute(
        select(Annotation).where(
            Annotation.auto_labels["source"].astext == "anomaly_detection",
            Annotation.auto_labels["anomaly_id"].astext == str(anomaly_event.id),
        )
    )
    if existing.scalar_one_or_none() is not None:
        logger.debug(
            "anomaly_label_exists anomaly_id=%s", anomaly_event.id
        )
        return None

    auto_labels: dict[str, Any] = {
        "source": "anomaly_detection",
        "anomaly_id": str(anomaly_event.id),
        "anomaly_type": anomaly_event.anomaly_type,
        "anomaly_score": anomaly_event.anomaly_score,
        "embedding_distance": anomaly_event.embedding_distance,
        "camera_node_id": anomaly_event.camera_node_id,
        "frame_timestamp": anomaly_event.frame_timestamp.isoformat(),
        "is_confirmed": anomaly_event.is_confirmed,
    }

    detected_objects: dict[str, Any] = {
        "anomaly_description": anomaly_event.description or "",
        "anomaly_type": anomaly_event.anomaly_type,
        "bounding_box": anomaly_event.bounding_box,
        "feedback_for_labeling": True,
    }

    annotation = Annotation(
        id=uuid4(),
        batch_id=batch_id,
        image_index=image_index,
        image_path=image_path or f"anomaly/{anomaly_event.camera_node_id}/{anomaly_event.id}",
        thumbnail_path=thumbnail_path or "",
        detected_objects=detected_objects,
        auto_labels=auto_labels,
        status=AnnotationStatus.AUTO_LABELED,
        quality_score=1.0,
    )
    db.add(annotation)
    await db.flush()

    logger.info(
        "anomaly_wired_to_queue anomaly_id=%s annotation_id=%s source=anomaly_detection",
        anomaly_event.id,
        annotation.id,
    )
    return annotation


async def get_anomaly_sourced_annotations(
    db: Any,
    camera_node_id: str | None = None,
    limit: int = 50,
    unresolved_only: bool = True,
) -> list[Any]:
    """Query annotations that originated from anomaly detection.

    This provides the labeling queue with a filtered view of anomaly-sourced
    items, distinguishable from auto-labels and human submissions.
    """
    from sqlalchemy import select

    from app.models.annotation import Annotation
    from app.models.enums import AnnotationStatus

    stmt = (
        select(Annotation)
        .where(Annotation.auto_labels["source"].astext == "anomaly_detection")
    )
    if camera_node_id is not None:
        stmt = stmt.where(
            Annotation.auto_labels["camera_node_id"].astext == camera_node_id
        )
    if unresolved_only:
        stmt = stmt.where(
            Annotation.status.in_([
                AnnotationStatus.AUTO_LABELED,
                AnnotationStatus.HUMAN_REVIEW,
                AnnotationStatus.QA_REVIEW,
            ])
        )
    stmt = stmt.order_by(Annotation.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Convenience: full pipeline run
# ---------------------------------------------------------------------------

def run_anomaly_pipeline(
    camera_id: str,
    frame_bytes: bytes | None = None,
    frame_rgb: Any | None = None,
    detections: list[dict] | None = None,
) -> dict[str, Any] | None:
    """Run the full embed -> score -> describe pipeline for a single frame.

    This is the main entry point for the live pipeline.  Returns ``None``
    when the camera is not yet ready (minimum data-volume guard) or when no
    anomaly is detected.

    Returns
    -------
    dict | None
        ``{"camera_id": ..., "embedding": ..., "score_result": ...,
          "description": ...}``  or ``None``.
    """
    from app.anomaly.scene_embedder import _extract_features

    embedder = get_scene_embedder()
    scorer = get_anomaly_scorer()
    describer = get_anomaly_describer()

    # Gate: minimum data volume
    if not embedder.is_ready(camera_id):
        # Still feed the frame to accumulate training data
        embedder.feed_frame(camera_id, frame_bytes=frame_bytes, frame_rgb=frame_rgb)
        return None

    # Encode
    embedding = embedder.encode(camera_id, frame_bytes=frame_bytes, frame_rgb=frame_rgb)
    if embedding is None:
        return None

    # Feed embedding to scorer (keeps GMM current)
    scorer.feed_embedding(camera_id, embedding)

    # Score
    score_result = scorer.score(camera_id, embedding)
    if score_result is None:
        return None

    # Describe
    description = describer.describe(
        camera_id,
        score_result,
        detections=detections,
    )

    # Compute reconstruction error for additional context
    raw_feat = _extract_features(frame_bytes=frame_bytes, frame_rgb=frame_rgb)
    recon_err = embedder.reconstruction_error(camera_id, raw_feat)

    return {
        "camera_id": camera_id,
        "embedding": embedding,
        "score_result": score_result,
        "description": description,
        "reconstruction_error": recon_err,
    }
