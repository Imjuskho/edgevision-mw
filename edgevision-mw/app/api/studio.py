from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import AnnotationStatus, DatasetStatus
from app.models.studio import (
    AnnotationAction,
    AnnotationSession,
)
from app.schemas.studio import (
    AnnotationsResponse,
    ExportJobCreate,
    ExportJobResponse,
    HealthScoreResponse,
    ImageListItem,
    ImageListResponse,
    SaveAnnotationRequest,
    SaveAnnotationResponse,
    SessionCreate,
    SessionResponse,
    StudioDatasetCreate,
    StudioDatasetResponse,
)

studio_router = APIRouter(prefix="/studio", tags=["Studio"])


async def _resolve_dataset(db: AsyncSession, identifier: str) -> Dataset:
    """Resolve a dataset by string dataset_id or UUID."""
    try:
        uid = UUID(identifier)
        ds = await db.get(Dataset, uid)
        if ds is not None:
            return ds
    except ValueError:
        pass
    stmt = select(Dataset).where(Dataset.dataset_id == identifier).limit(1)
    ds = (await db.execute(stmt)).scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {identifier}")
    return ds


async def _get_or_create_studio_node(db: AsyncSession):
    from app.models.enums import NodeCategory, NodeStatus, PIIMode
    from app.models.node import Node

    stmt = select(Node).where(Node.node_id == "studio-node").limit(1)
    node = (await db.execute(stmt)).scalar_one_or_none()
    if node is not None:
        return node

    node = Node(
        node_id="studio-node",
        district="Studio",
        latitude=0.0,
        longitude=0.0,
        category=NodeCategory.ROAD,
        hardware_profile={"type": "studio"},
        network_config={},
        capture_schedule="manual",
        interest_classes=[],
        pii_mode=PIIMode.MODERATE,
        firmware_version="1.0.0",
        public_key=b"\x00" * 32,
        status=NodeStatus.ONLINE,
        is_enabled=True,
    )
    db.add(node)
    await db.flush()
    return node


async def _get_or_create_studio_batch(db: AsyncSession, ds: Dataset):
    from app.models.enums import BatchStatus
    from app.models.ingestion import IngestionBatch

    stmt = select(IngestionBatch).where(IngestionBatch.batch_id.startswith(f"STUDIO-{ds.dataset_id}")).limit(1)
    batch = (await db.execute(stmt)).scalar_one_or_none()
    if batch is not None:
        return batch

    node = await _get_or_create_studio_node(db)
    batch = IngestionBatch(
        batch_id=f"STUDIO-{ds.dataset_id}-{uuid4().hex[:8]}",
        node_id=node.id,
        hub_id="studio-hub",
        event_count=0,
        file_size_bytes=0,
        checksum_sha256="",
        node_signature=b"\x00" * 64,
        compression_codec="none",
        status=BatchStatus.INGESTED,
        quality_scores={},
    )
    db.add(batch)
    await db.flush()
    return batch


async def _ensure_annotations_exist_for_dataset(db: AsyncSession, ds: Dataset) -> None:
    from app.services.dataset_sync import sync_dataset_pipeline

    await sync_dataset_pipeline(db, ds)


def _slugify_dataset_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:36] or f"dataset-{uuid4().hex[:8]}"


def _dataset_to_studio_response(ds: Dataset) -> StudioDatasetResponse:
    meta = ds.metadata_ or {}
    return StudioDatasetResponse(
        id=ds.id,
        dataset_id=ds.dataset_id,
        name=ds.name,
        status=ds.status.value if hasattr(ds.status, "value") else str(ds.status),
        sample_count=ds.sample_count,
        source_type=meta.get("source_type"),
        description=meta.get("description"),
        created_at=ds.created_at,
        updated_at=ds.updated_at,
    )


@studio_router.post("/datasets", response_model=StudioDatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    body: StudioDatasetCreate,
    user: dict = Depends(require_role(["ADMIN", "OPERATOR"])),
    db: AsyncSession = Depends(get_db),
):
    dataset_id = (body.dataset_id or _slugify_dataset_id(body.name)).strip()
    if not dataset_id:
        raise HTTPException(status_code=400, detail="dataset_id cannot be empty")

    existing = await db.execute(select(Dataset).where(Dataset.dataset_id == dataset_id).limit(1))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Dataset already exists: {dataset_id}")

    metadata: dict = {"source_type": body.source_type}
    if body.description:
        metadata["description"] = body.description

    ds = Dataset(
        dataset_id=dataset_id,
        name=body.name.strip(),
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
        metadata_=metadata,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return _dataset_to_studio_response(ds)


@studio_router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    body: SessionCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(user["sub"])
    ds = await _resolve_dataset(db, body.dataset_id)
    await _ensure_annotations_exist_for_dataset(db, ds)

    session = AnnotationSession(
        user_id=user_id,
        dataset_id=ds.id,
        started_at=datetime.now(UTC),
        image_count=0,
        annotations_created=0,
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@studio_router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sess = await db.get(AnnotationSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.user_id != UUID(user["sub"]):
        raise HTTPException(status_code=403, detail="Not your session")
    return sess


@studio_router.get(
    "/datasets/{dataset_id}/images",
    response_model=ImageListResponse,
)
async def list_images(
    dataset_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, dataset_id)
    from app.services.dataset_sync import sync_dataset_pipeline

    await sync_dataset_pipeline(db, ds)
    await db.commit()
    await db.refresh(ds)

    stmt = select(Annotation).where(Annotation.dataset_id == ds.id).order_by(Annotation.image_index)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    images = [
        ImageListItem(
            index=a.image_index,
            annotation_id=a.id,
            image_path=a.image_path,
            thumbnail_path=a.thumbnail_path,
            status=a.status.value if hasattr(a.status, "value") else str(a.status),
            has_human_labels=a.human_labels is not None,
        )
        for a in rows
    ]
    return ImageListResponse(
        dataset_id=ds.id,
        total=total,
        page=page,
        page_size=page_size,
        images=images,
    )


@studio_router.post(
    "/annotations/save",
    response_model=SaveAnnotationResponse,
    status_code=201,
)
async def save_annotation(
    body: SaveAnnotationRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sess = await db.get(AnnotationSession, body.session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.user_id != UUID(user["sub"]):
        raise HTTPException(status_code=403, detail="Not your session")

    stmt = (
        select(Annotation)
        .where(
            Annotation.dataset_id == sess.dataset_id,
            Annotation.image_index == body.image_index,
        )
        .limit(1)
    )
    annotation = (await db.execute(stmt)).scalar_one_or_none()

    if annotation is None:
        raise HTTPException(status_code=404, detail="Image annotation not found")

    prev_labels = annotation.human_labels or {}
    was_ai_draft = bool(prev_labels.get("ai_draft"))
    human_labels: dict = {
        "boxes": [b.model_dump() for b in body.annotations],
        "tool": body.tool_used,
    }
    if was_ai_draft:
        human_labels["source"] = "human_corrected"
        human_labels["ai_draft"] = False
    elif prev_labels.get("source"):
        human_labels["source"] = prev_labels["source"]

    annotation.human_labels = human_labels

    action = AnnotationAction(
        session_id=sess.id,
        annotation_id=annotation.id,
        action_type="save_labels",
        image_index=body.image_index,
        payload={
            "annotations": [b.model_dump() for b in body.annotations],
            "tool": body.tool_used,
        },
    )
    db.add(action)

    sess.annotations_created += 1

    await db.commit()
    await db.refresh(action)

    return SaveAnnotationResponse(
        action_id=action.id,
        annotation_id=annotation.id,
        saved=True,
        image_index=body.image_index,
        annotation_count=len(body.annotations),
    )


@studio_router.get(
    "/annotations/{annotation_id}",
    response_model=AnnotationsResponse,
)
async def get_annotation_data(
    annotation_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    annotation = await db.get(Annotation, annotation_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")

    boxes: list = []
    tool_used: str | None = None
    qa_labels: dict | None = None
    label_source: str | None = None
    ai_draft = False
    frame_width: int | None = None
    frame_height: int | None = None

    if annotation.human_labels and "boxes" in annotation.human_labels:
        boxes = annotation.human_labels["boxes"]
        tool_used = annotation.human_labels.get("tool")
        label_source = annotation.human_labels.get("source")
        ai_draft = bool(annotation.human_labels.get("ai_draft"))
    if annotation.qa_labels:
        qa_labels = annotation.qa_labels

    if annotation.dataset_id:
        from app.models.image import ImageRecord

        img_row = await db.get(ImageRecord, annotation.id)
        if img_row is not None:
            frame_width = img_row.width or None
            frame_height = img_row.height or None

    if not frame_width or not frame_height:
        try:
            from app.core.config import settings
            from app.core.dependencies import get_minio_client

            mc = await get_minio_client()
            raw = mc.get_object(settings.MINIO_BUCKET, annotation.image_path).read()
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(raw))
            frame_width, frame_height = img.size
        except Exception:
            frame_width = frame_width or None
            frame_height = frame_height or None

    return AnnotationsResponse(
        annotation_id=annotation.id,
        image_index=annotation.image_index,
        annotations=boxes,
        tool_used=tool_used,
        qa_labels=qa_labels,
        detected_objects=_extract_detected_objects(annotation),
        frame_width=frame_width,
        frame_height=frame_height,
        label_source=label_source,
        ai_draft=ai_draft,
    )


@studio_router.get("/images/{annotation_id}/serve")
async def serve_image(
    annotation_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    annotation = await db.get(Annotation, annotation_id)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")

    try:
        from app.core.config import settings
        from app.core.minio_helper import get_object_bytes

        data = await get_object_bytes(settings.MINIO_BUCKET, annotation.image_path)
        ext = annotation.image_path.rsplit(".", 1)[-1].lower() if "." in annotation.image_path else "png"
        media_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/png")
        return StreamingResponse(
            iter([data]),
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{annotation.image_path.split("/")[-1]}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image fetch failed: {e!s}")


@studio_router.get(
    "/datasets/{dataset_id}/health",
    response_model=HealthScoreResponse,
)
async def get_health(
    dataset_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _resolve_dataset(db, dataset_id)

    total_stmt = select(func.count()).where(Annotation.dataset_id == ds.id)
    total = (await db.execute(total_stmt)).scalar() or 0

    labeled_stmt = select(func.count()).where(
        Annotation.dataset_id == ds.id,
        Annotation.human_labels.isnot(None),
    )
    labeled = (await db.execute(labeled_stmt)).scalar() or 0

    certified_stmt = select(func.count()).where(
        Annotation.dataset_id == ds.id,
        Annotation.is_certified,
    )
    certified = (await db.execute(certified_stmt)).scalar() or 0

    completeness = (labeled / total * 100) if total > 0 else 0.0
    accuracy = (certified / labeled * 100) if labeled > 0 else 0.0
    overall = (completeness * 0.6 + accuracy * 0.4) if total > 0 else 0.0

    recs = []
    if completeness < 50:
        recs.append("Less than 50% of images have human labels — prioritize labeling.")
    if accuracy < 80 and labeled > 0:
        recs.append("QA pass rate below 80% — review labeling guidelines.")
    if total == 0:
        recs.append("Dataset has no annotations — run ingestion first.")

    return HealthScoreResponse(
        dataset_id=ds.id,
        overall_score=round(overall, 2),
        completeness_pct=round(completeness, 2),
        consistency_pct=100.0,
        accuracy_pct=round(accuracy, 2),
        timeliness_pct=100.0,
        recommendations=recs,
    )


@studio_router.post(
    "/exports",
    response_model=ExportJobResponse,
    status_code=201,
)
async def create_export(
    body: ExportJobCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.studio import ExportJob

    ds = await _resolve_dataset(db, body.dataset_id)

    job = ExportJob(
        dataset_id=ds.id,
        user_id=UUID(user["sub"]),
        status="PROCESSING",
        format=body.format,
        include_images=body.include_images,
        include_annotations=body.include_annotations,
        include_metadata=body.include_metadata,
        progress_pct=0.0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    try:
        from app.workers.tasks import _export_build_async

        await db.commit()
        await _export_build_async(
            str(job.id),
            ds.dataset_id,
            body.format,
            {"train": 0.8, "val": 0.1, "test": 0.1},
            None,
            [],
            True,
        )
    except Exception as exc:
        job.status = "FAILED"
        job.error_message = str(exc)[:500]
        await db.commit()

    await db.refresh(job)
    return job


@studio_router.get("/exports/{export_id}", response_model=ExportJobResponse)
async def get_export(
    export_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.studio import ExportJob

    job = await db.get(ExportJob, export_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    if job.user_id != UUID(user["sub"]):
        raise HTTPException(status_code=403, detail="Not your export job")
    return job


@studio_router.get("/exports/{export_id}/download")
async def download_export(
    export_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    from app.models.studio import ExportJob

    job = await db.get(ExportJob, export_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    if job.user_id != UUID(user["sub"]):
        raise HTTPException(status_code=403, detail="Not your export job")
    if job.status != "COMPLETED":
        raise HTTPException(status_code=400, detail=f"Export status: {job.status}")

    # Try MinIO first
    try:
        from app.core.config import settings
        from app.core.dependencies import get_minio_client

        mc = await get_minio_client()
        object_name = f"exports/{export_id}/coco.json"
        response = mc.get_object(settings.MINIO_BUCKET, object_name)
        return StreamingResponse(
            iter([response.read()]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="coco_{export_id}.json"'},
        )
    except Exception:
        pass

    # Fallback: local filesystem
    local_path = f"/tmp/edgevision-exports/{export_id}/coco.json"
    if os.path.exists(local_path):
        return StreamingResponse(
            iter([open(local_path, "rb").read()]),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="coco_{export_id}.json"'},
        )

    raise HTTPException(status_code=404, detail="Export file not found")


# ─── TurboReview endpoints ──────────────────────────────────────────────────

_ACTION_TO_DECISION = {
    "approve": "approved",
    "reject": "rejected",
    "flag": "flagged",
    "approved": "approved",
    "rejected": "rejected",
    "flagged": "flagged",
}

_MAX_REFINE_MASK_POINTS = 32
_CUBOID_CORNER_COUNT = 8


def _resolve_review_decision(action_item: dict) -> str | None:
    """Prefer ``decision``; fall back to legacy ``action`` alias."""
    decision = action_item.get("decision")
    if isinstance(decision, str):
        mapped = _ACTION_TO_DECISION.get(decision)
        if mapped:
            return mapped
    legacy = action_item.get("action")
    if isinstance(legacy, str):
        return _ACTION_TO_DECISION.get(legacy)
    return None


def _validate_refines(refines: list) -> list[dict]:
    """Validate QA refines: normalized coords, mask ≤32 points, cuboid 8 corners."""
    if not isinstance(refines, list):
        raise HTTPException(status_code=422, detail="refines must be a list")

    validated: list[dict] = []
    for idx, item in enumerate(refines):
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail=f"refines[{idx}] must be an object")

        try:
            object_index = int(item.get("object_index", -1))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"refines[{idx}].object_index invalid") from exc
        if object_index < 0:
            raise HTTPException(status_code=422, detail=f"refines[{idx}].object_index must be >= 0")

        entry: dict = {"object_index": object_index}

        if "mask" in item and item["mask"] is not None:
            mask = item["mask"]
            if not isinstance(mask, list):
                raise HTTPException(status_code=422, detail=f"refines[{idx}].mask must be a list")
            if len(mask) > _MAX_REFINE_MASK_POINTS:
                raise HTTPException(
                    status_code=422,
                    detail=f"refines[{idx}].mask exceeds {_MAX_REFINE_MASK_POINTS} points",
                )
            norm_mask: list[list[float]] = []
            for p_i, point in enumerate(mask):
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    raise HTTPException(
                        status_code=422,
                        detail=f"refines[{idx}].mask[{p_i}] must be [x, y]",
                    )
                try:
                    x, y = float(point[0]), float(point[1])
                except (TypeError, ValueError) as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=f"refines[{idx}].mask[{p_i}] coords must be numbers",
                    ) from exc
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise HTTPException(
                        status_code=422,
                        detail=f"refines[{idx}].mask[{p_i}] must be normalized 0..1",
                    )
                norm_mask.append([x, y])
            entry["mask"] = norm_mask

        if "bbox_3d" in item and item["bbox_3d"] is not None:
            bbox_3d = item["bbox_3d"]
            if not isinstance(bbox_3d, dict):
                raise HTTPException(status_code=422, detail=f"refines[{idx}].bbox_3d must be an object")
            corners = bbox_3d.get("corners")
            if not isinstance(corners, list):
                raise HTTPException(
                    status_code=422,
                    detail=f"refines[{idx}].bbox_3d.corners must be a list",
                )
            if len(corners) != _CUBOID_CORNER_COUNT:
                raise HTTPException(
                    status_code=422,
                    detail=f"refines[{idx}].bbox_3d.corners must have exactly {_CUBOID_CORNER_COUNT} points",
                )
            norm_corners: list[list[float]] = []
            for c_i, corner in enumerate(corners):
                if not isinstance(corner, (list, tuple)) or len(corner) < 2:
                    raise HTTPException(
                        status_code=422,
                        detail=f"refines[{idx}].bbox_3d.corners[{c_i}] must be [x, y, z?]",
                    )
                try:
                    x, y = float(corner[0]), float(corner[1])
                    z = float(corner[2]) if len(corner) > 2 else 0.0
                except (TypeError, ValueError) as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=f"refines[{idx}].bbox_3d.corners[{c_i}] coords must be numbers",
                    ) from exc
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    raise HTTPException(
                        status_code=422,
                        detail=f"refines[{idx}].bbox_3d.corners[{c_i}] x/y must be normalized 0..1",
                    )
                norm_corners.append([x, y, z])
            entry["bbox_3d"] = {"corners": norm_corners}

        validated.append(entry)

    return validated


def _extract_detected_objects(ann: Annotation) -> list[dict]:
    """Passthrough refine targets from detected_objects (mask, bbox_3d, confidence, track_id)."""
    detected = ann.detected_objects if isinstance(ann.detected_objects, dict) else {}
    objects = detected.get("objects", [])
    if not isinstance(objects, list):
        return []

    result: list[dict] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        entry: dict = {}
        if "mask" in obj:
            entry["mask"] = obj["mask"]
        if "bbox_3d" in obj:
            entry["bbox_3d"] = obj["bbox_3d"]
        if "confidence" in obj:
            entry["confidence"] = obj["confidence"]
        if "track_id" in obj:
            entry["track_id"] = obj["track_id"]
        if "class_name" in obj:
            entry["class_name"] = obj["class_name"]
        elif "label" in obj:
            entry["class_name"] = obj["label"]
        if "taxonomy_label" in obj:
            entry["taxonomy_label"] = obj["taxonomy_label"]
        if "bbox" in obj:
            entry["bbox"] = obj["bbox"]
        if "mask_format" in obj:
            entry["mask_format"] = obj["mask_format"]
        result.append(entry)
    return result


@studio_router.get("/sessions/{session_id}/review-queue")
async def review_queue(
    session_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.studio import AnnotationSession

    sess = await db.get(AnnotationSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.user_id != UUID(user["sub"]):
        raise HTTPException(status_code=403, detail="Not your session")

    stmt = (
        select(Annotation).where(Annotation.dataset_id == sess.dataset_id).order_by(Annotation.image_index).limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    images = []
    for a in rows:
        labels_data = a.human_labels or {}
        boxes = labels_data.get("boxes", []) if isinstance(labels_data, dict) else []
        detected_raw = a.detected_objects if isinstance(a.detected_objects, dict) else {}
        images.append(
            {
                "id": str(a.id),
                "image_path": a.image_path,
                "index": a.image_index,
                "image_index": a.image_index,
                "status": "pending" if not a.is_certified else "approved",
                "annotations": [
                    {
                        "className": b.get("label", ""),
                        "confidence": b.get("confidence", 1.0),
                        "bbox": [
                            b.get("x", 0),
                            b.get("y", 0),
                            b.get("width", 0),
                            b.get("height", 0),
                        ],
                        "polygon": b.get("polygon"),
                    }
                    for b in boxes
                ],
                "has_human_labels": a.human_labels is not None,
                "ai_draft": bool(labels_data.get("ai_draft")),
                "label_source": labels_data.get("source"),
                "live_capture": bool(detected_raw.get("live_capture")),
                "orientation": detected_raw.get("orientation"),
                "depth_available": detected_raw.get("depth_available"),
                "detected_objects": _extract_detected_objects(a),
            }
        )

    return {"images": images, "total": len(images)}


@studio_router.post("/sessions/{session_id}/review-submit")
async def review_submit(
    session_id: UUID,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.studio import AnnotationAction, AnnotationSession

    sess = await db.get(AnnotationSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if sess.user_id != UUID(user["sub"]):
        raise HTTPException(status_code=403, detail="Not your session")

    actions = body.get("actions", [])
    results = []

    for action in actions:
        image_id = action.get("image_id")
        decision = _resolve_review_decision(action)

        if not image_id or decision not in ("approved", "rejected", "flagged"):
            continue

        ann = await db.get(Annotation, UUID(image_id))
        if ann is None:
            continue

        original_human_labels = ann.human_labels

        if decision == "approved":
            ann.is_certified = True
            ann.status = AnnotationStatus.CERTIFIED
        elif decision == "rejected":
            ann.status = AnnotationStatus.REJECTED
        else:
            # flagged — keep PENDING for senior review
            ann.status = AnnotationStatus.PENDING
            ann.is_certified = False

        if "refines" in action and action["refines"] is not None:
            validated_refines = _validate_refines(action["refines"])
            qa = dict(ann.qa_labels) if isinstance(ann.qa_labels, dict) else {}
            qa["refines"] = validated_refines
            ann.qa_labels = qa
            refine_record = AnnotationAction(
                session_id=sess.id,
                annotation_id=ann.id,
                action_type="refine",
                image_index=ann.image_index,
                payload={"refines": validated_refines},
            )
            db.add(refine_record)

        # Never mutate human_labels during review submit
        ann.human_labels = original_human_labels

        record = AnnotationAction(
            session_id=sess.id,
            annotation_id=ann.id,
            action_type=f"review_{decision}",
            image_index=ann.image_index,
            payload={"decision": decision},
        )
        db.add(record)
        results.append({"image_id": image_id, "decision": decision})

    await db.commit()

    return {
        "processed": len(results),
        "results": results,
    }
