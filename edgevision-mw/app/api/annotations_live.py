from __future__ import annotations

import json
from datetime import datetime
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.features import require_role_and_feature
from app.core.logging import get_logger
from app.core.tenant import get_current_tenant_id
from app.schemas.perception import EventRulesUpdate, PerceptionEventPage

logger = get_logger("edgevision.api.annotations_live")

annotations_live_router = APIRouter(prefix="/annotations", tags=["Live Annotation"])


def _parse_json_array(raw: str | None, field: str, *, allow_none: bool = True) -> list | None:
    if not raw:
        if allow_none:
            return None
        raise HTTPException(status_code=422, detail=f"{field} is required")
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError(f"{field} must be a JSON array")
        return parsed
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {field} JSON: {exc}")


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

    ann_list = _parse_json_array(annotations, "annotations", allow_none=False) or []
    mask_list = _parse_json_array(masks, "masks")
    bbox_3d_list = _parse_json_array(bbox_3d, "bbox_3d")

    if mask_list and len(mask_list) != len(ann_list):
        raise HTTPException(status_code=422, detail="masks array length must match annotations")

    if bbox_3d_list and len(bbox_3d_list) != len(ann_list):
        raise HTTPException(status_code=422, detail="bbox_3d array length must match annotations")

    from app.services.live_capture import save_live_capture

    try:
        return await save_live_capture(
            db,
            content=content,
            ann_list=ann_list,
            source=source,
            dataset_id=dataset_id,
            confidence_threshold=confidence_threshold,
            orientation=orientation,
            depth_available=depth_available,
            user_id=user_id,
            tenant_id=tenant_id,
            masks=mask_list,
            bbox_3d=bbox_3d_list,
            capture_reason="manual",
        )
    except ValueError as exc:
        if str(exc).startswith("Dataset"):
            raise HTTPException(status_code=404, detail=str(exc))
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@annotations_live_router.get("/events", response_model=PerceptionEventPage)
async def list_perception_events(
    event_type: str | None = None,
    rule_id: str | None = None,
    track_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(require_role(["ADMIN", "OPERATOR", "ANNOTATOR", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    from app.services.perception_events import list_perception_events

    items, total = await list_perception_events(
        db,
        event_type=event_type,
        rule_id=rule_id,
        track_id=track_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@annotations_live_router.get("/event-rules")
async def get_event_rules(
    user: dict = Depends(require_role(["ADMIN", "OPERATOR", "ANNOTATOR", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    from app.services.perception_events import get_event_rules

    return {"rules": await get_event_rules(db)}


@annotations_live_router.put("/event-rules")
async def update_event_rules(
    payload: EventRulesUpdate = Body(...),
    user: dict = Depends(require_role(["ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    from app.services.perception_events import update_event_rules

    try:
        rules = await update_event_rules(
            db,
            [rule.model_dump() for rule in payload.rules],
            actor_id=user["sub"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"rules": rules}


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
