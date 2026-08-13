from __future__ import annotations

import json
from typing import Literal
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.mask_utils import mask_to_rle, polygon_to_mask, pycocotools_available
from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.features import require_role_and_feature
from app.core.logging import get_logger
from app.core.tenant import get_current_tenant_id
from app.models.annotation import Annotation
from app.models.enums import AnnotationStatus

logger = get_logger("edgevision.api.annotations_live")

annotations_live_router = APIRouter(prefix="/annotations", tags=["Live Annotation"])


def _attach_mask_rle(objects: list, width: int, height: int) -> None:
    """Encode polygon masks as COCO RLE when pycocotools is available."""
    if width <= 0 or height <= 0:
        return
    if not pycocotools_available():
        logger.warning("mask_rle_unavailable", reason="pycocotools_not_installed")
        return

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if obj.get("mask_rle"):
            continue
        polygon = obj.get("mask")
        if not isinstance(polygon, list) or len(polygon) < 3:
            continue
        if obj.get("mask_format") not in (None, "polygon"):
            continue
        mask = polygon_to_mask(polygon, width, height)
        if not mask.any():
            continue
        try:
            mask_rle = mask_to_rle(mask)
        except ImportError:
            logger.warning("mask_rle_unavailable", reason="pycocotools_not_installed")
            return
        obj["mask_rle"] = mask_rle
        obj["mask_format"] = "rle"


@annotations_live_router.post("/live", status_code=status.HTTP_201_CREATED)
async def save_live_annotation(
    file: UploadFile = File(..., description="JPEG frame image"),
    annotations: str = Form(..., description="JSON array of AI predictions"),
    source: str = Form("live_camera", description="Source: live_camera, screen, drone"),
    dataset_id: str = Form(None, description="Optional dataset ID to associate with"),
    confidence_threshold: float = Form(0.35, description="Confidence threshold used at inference"),
    orientation: Literal["normal", "mirrored"] = Form("normal", description="Frame orientation: normal or mirrored"),
    depth_available: bool = Form(False, description="Whether ONNX depth was used at inference"),
    masks: str = Form(None, description="Optional JSON array of mask polygons aligned with annotations"),
    bbox_3d: str = Form(None, description="Optional JSON array of 3D bbox payloads aligned with annotations"),
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR", "ANNOTATOR", "QA"], "liveAnnotate")),
    db: AsyncSession = Depends(get_db),
):
    user_id = UUID(user["sub"])
    tenant_id = get_current_tenant_id()

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    # Apply face privacy blur before persisting live captures (PII mode is STRICT on live nodes).
    faces_blurred = 0
    try:
        import cv2
        import numpy as np

        from app.ai.face_privacy import get_face_blurrer

        blurrer = get_face_blurrer()
        if blurrer.is_loaded():
            arr = np.frombuffer(content, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                faces = blurrer.detect_faces(img)
                if faces:
                    content = blurrer.process_image_bytes(content)
                    faces_blurred = len(faces)
        else:
            logger.warning("face_blur_skipped", reason="detector_not_loaded")
    except Exception as exc:
        logger.warning("face_blur_failed", error=str(exc))

    # Parse annotations JSON
    try:
        ann_list = json.loads(annotations)
        if not isinstance(ann_list, list):
            raise ValueError("annotations must be a JSON array")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid annotations JSON: {exc}")

    mask_list: list | None = None
    if masks:
        try:
            mask_list = json.loads(masks)
            if not isinstance(mask_list, list):
                raise ValueError("masks must be a JSON array")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid masks JSON: {exc}")

    bbox_3d_list: list | None = None
    if bbox_3d:
        try:
            bbox_3d_list = json.loads(bbox_3d)
            if not isinstance(bbox_3d_list, list):
                raise ValueError("bbox_3d must be a JSON array")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid bbox_3d JSON: {exc}")

    if mask_list and len(mask_list) != len(ann_list):
        raise HTTPException(status_code=422, detail="masks array length must match annotations")

    if bbox_3d_list and len(bbox_3d_list) != len(ann_list):
        raise HTTPException(status_code=422, detail="bbox_3d array length must match annotations")

    # Attach masks to annotation objects when provided
    if mask_list:
        enriched = []
        for i, ann in enumerate(ann_list):
            item = dict(ann) if isinstance(ann, dict) else {"class_name": str(ann)}
            mask_data = mask_list[i] if i < len(mask_list) else None
            if mask_data:
                if isinstance(mask_data, dict) and mask_data.get("format") == "rle":
                    item["mask"] = mask_data
                    item["mask_format"] = "rle"
                elif isinstance(mask_data, list):
                    item["mask"] = mask_data
                    item["mask_format"] = "polygon"
            enriched.append(item)
        ann_list = enriched

    if bbox_3d_list:
        enriched = []
        for i, ann in enumerate(ann_list):
            item = dict(ann) if isinstance(ann, dict) else {"class_name": str(ann)}
            box3d = bbox_3d_list[i] if i < len(bbox_3d_list) else None
            if box3d:
                item["bbox_3d"] = box3d
            enriched.append(item)
        ann_list = enriched

    # Store frame in MinIO
    ts = __import__("datetime").datetime.utcnow().isoformat().replace(":", "-")
    object_key = f"tenants/{tenant_id}/live-captures/{ts}_{uuid4().hex}.jpg"

    from app.core.config import settings
    from app.core.minio_helper import put_object

    try:
        await put_object(settings.MINIO_BUCKET, object_key, content, "image/jpeg")
    except Exception as exc:
        logger.error("minio_upload_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to store frame: {exc}")

    # Create annotation record
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(content))
        width, height = img.size
    except Exception:
        width, height = 0, 0

    has_mask_rle = False

    # Resolve optional dataset — live frames must land in the studio catalog when requested.
    ds = None
    if dataset_id:
        from app.services.dataset_sync import resolve_dataset

        ds = await resolve_dataset(db, dataset_id)
        if ds is None:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    frame_id = uuid4()
    checksum = __import__("hashlib").sha256(content).hexdigest()

    if ds is not None:
        from app.models.image import ImageRecord

        db.add(
            ImageRecord(
                id=frame_id,
                storage_key=object_key,
                thumbnail_key=object_key,
                filename=f"live_{ts}.jpg",
                content_type="image/jpeg",
                size_bytes=len(content),
                width=width,
                height=height,
                source=source,
                metadata_={
                    "live_capture": True,
                    "annotation_count": len(ann_list),
                    "confidence_threshold": confidence_threshold,
                    "orientation": orientation,
                    "has_mask_rle": False,
                },
                dataset_id=ds.id,
                uploaded_by=user_id,
                tenant_id=tenant_id,
                checksum_sha256=checksum,
            )
        )
        await db.flush()

    from app.models.enums import BatchStatus, NodeStatus
    from app.models.ingestion import IngestionBatch
    from app.models.node import Node, NodeCategory, PIIMode

    if ds is not None:
        from app.api.studio import _get_or_create_studio_batch

        batch = await _get_or_create_studio_batch(db, ds)
        max_idx = (
            await db.execute(
                sa.select(sa.func.max(Annotation.image_index)).where(Annotation.dataset_id == ds.id)
            )
        ).scalar()
        image_index = (max_idx if max_idx is not None else -1) + 1
    else:
        node_result = await db.execute(sa.select(Node).limit(1))
        live_node = node_result.scalar_one_or_none()
        if live_node is None:
            live_node = Node(
                node_id=f"LIVE-{uuid4().hex[:12]}",
                district="virtual",
                latitude=0.0,
                longitude=0.0,
                category=NodeCategory.ROAD,
                hardware_profile={"type": "live-capture"},
                network_config={},
                capture_schedule="on-demand",
                interest_classes=[],
                pii_mode=PIIMode.STRICT,
                firmware_version="0.0.0",
                public_key=b"\x00" * 32,
                status=NodeStatus.ONLINE,
                is_enabled=True,
            )
            db.add(live_node)
            await db.flush()

        batch = IngestionBatch(
            batch_id=f"LIVE-{uuid4().hex[:12]}",
            node_id=live_node.id,
            hub_id="live-capture",
            event_count=1,
            file_size_bytes=len(content),
            checksum_sha256=checksum,
            node_signature=b"\x00" * 64,
            compression_codec="raw",
            status=BatchStatus.INGESTED,
            quality_scores={},
        )
        db.add(batch)
        await db.flush()
        image_index = 0

    detected_payload: dict | list
    if isinstance(ann_list, list):
        _attach_mask_rle(ann_list, width, height)
        has_mask_rle = any(
            isinstance(o, dict) and o.get("mask_rle") for o in ann_list
        )
        detected_payload = {
            "objects": ann_list,
            "source": source,
            "orientation": orientation,
            "depth_available": depth_available,
            "live_capture": True,
        }
    else:
        detected_payload = ann_list if ann_list else {"objects": [], "orientation": orientation}

    record = Annotation(
        id=frame_id if ds is not None else uuid4(),
        batch_id=batch.id,
        image_index=image_index,
        image_path=object_key,
        thumbnail_path=object_key,
        detected_objects=detected_payload,
        auto_labels={"source": source, "ai_assisted": True, "model_type": "live_inference"},
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
        annotator_id=user_id,
        dataset_id=ds.id if ds is not None else None,
    )

    if ds is not None and isinstance(ann_list, list) and ann_list and width > 0 and height > 0:
        from app.services.live_label_bridge import live_detections_to_studio_boxes

        studio_boxes = live_detections_to_studio_boxes(ann_list, width, height)
        if studio_boxes:
            tool = "polygon" if any(b.get("polygon") for b in studio_boxes) else "bbox"
            record.human_labels = {
                "boxes": studio_boxes,
                "tool": tool,
                "source": "live_ai_assisted",
                "ai_draft": True,
            }

    db.add(record)

    if ds is not None and has_mask_rle:
        from app.models.image import ImageRecord

        img_row = await db.get(ImageRecord, frame_id)
        if img_row is not None:
            meta = dict(img_row.metadata_ or {})
            meta["has_mask_rle"] = True
            img_row.metadata_ = meta

    if ds is not None:
        from app.services.dataset_sync import refresh_dataset_sample_count

        await refresh_dataset_sample_count(db, ds)

    await db.commit()
    await db.refresh(record)

    from app.api.metrics import annotations_total

    annotations_total.labels(status="created", label="live").inc()

    logger.info(
        "live_annotation_saved",
        annotation_id=str(record.id),
        object_count=len(ann_list),
        source=source,
        has_mask_rle=has_mask_rle,
    )

    return {
        "id": str(record.id),
        "annotation_id": str(record.id),
        "image_index": image_index,
        "image_path": object_key,
        "annotations_count": len(ann_list) if isinstance(ann_list, list) else 0,
        "source": source,
        "dataset_id": ds.dataset_id if ds is not None else None,
        "width": width,
        "height": height,
        "orientation": orientation,
        "depth_available": depth_available,
        "has_mask_rle": has_mask_rle,
        "faces_blurred": faces_blurred > 0,
        "ai_draft": bool(record.human_labels and record.human_labels.get("ai_draft")),
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@annotations_live_router.get("/live/checksums")
async def recent_live_checksums(
    limit: int = 200,
    user: dict = Depends(require_role(["ADMIN", "OPERATOR", "ANNOTATOR", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    """Return recent live-capture checksums for offline sync reconciliation."""
    from app.models.image import ImageRecord

    tenant_id = get_current_tenant_id()
    stmt = (
        sa.select(ImageRecord.checksum_sha256, ImageRecord.id)
        .where(ImageRecord.tenant_id == tenant_id)
        .where(ImageRecord.source.in_(["live_camera", "screen", "drone"]))
        .where(ImageRecord.checksum_sha256.isnot(None))
        .order_by(ImageRecord.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return {
        "checksums": [r[0] for r in rows if r[0]],
        "count": len(rows),
    }
