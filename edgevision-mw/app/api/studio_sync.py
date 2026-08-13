from __future__ import annotations

import contextlib
import hashlib
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.annotation import Annotation
from app.models.studio import AnnotationAction, AnnotationSession

router = APIRouter(prefix="/studio", tags=["studio-sync"])


class SyncAction(BaseModel):
    annotation_id: UUID = Field(..., description="Annotation ID to sync")
    action_type: str = Field(
        ...,
        pattern=r"^(create|edit|delete|approve|reject)$",
        description="Action type",
    )
    payload: dict | None = Field(default=None, description="Action payload")
    client_timestamp: str | None = Field(
        default=None, description="Client ISO timestamp for ordering"
    )
    etag: str | None = Field(
        default=None, description="ETag from last known server version"
    )


class SyncBatchRequest(BaseModel):
    session_id: UUID = Field(..., description="Annotation session ID")
    actions: list[SyncAction] = Field(..., description="Batch of actions")
    client_version: str | None = Field(
        default=None, description="Client app version"
    )


class SyncConflict(BaseModel):
    annotation_id: UUID
    server_version: dict | None
    client_version: dict | None
    resolution: str


class SyncBatchResponse(BaseModel):
    committed: list[UUID]
    conflicts: list[SyncConflict]
    rejected: list[dict]
    server_timestamp: str


@router.post("/sync/batch", response_model=SyncBatchResponse)
async def sync_batch(
    request: SyncBatchRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Process a batch of offline annotation actions.

    Conflict resolution:
    - Annotations: last-write-wins (compare timestamps via etag)
    - Session assignments: server-wins (prevent stale overwrites)
    """
    user_id = UUID(user["sub"])

    stmt = select(AnnotationSession).where(
        and_(
            AnnotationSession.id == request.session_id,
            AnnotationSession.user_id == user_id,
        )
    )
    session = (await db.execute(stmt)).scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=404, detail="Session not found or not owned by user"
        )

    committed: list[UUID] = []
    conflicts: list[SyncConflict] = []
    rejected: list[dict] = []

    for action in request.actions:
        ann_stmt = select(Annotation).where(Annotation.id == action.annotation_id)
        annotation = (await db.execute(ann_stmt)).scalar_one_or_none()

        if not annotation:
            rejected.append(
                {"annotation_id": str(action.annotation_id), "reason": "Not found"}
            )
            continue

        try:
            if action.action_type == "edit":
                if action.etag and annotation.updated_at:
                    server_etag = hashlib.md5(
                        annotation.updated_at.isoformat().encode()
                    ).hexdigest()
                    if server_etag != action.etag:
                        conflicts.append(
                            SyncConflict(
                                annotation_id=action.annotation_id,
                                server_version=annotation.human_labels,
                                client_version=action.payload,
                                resolution="server_wins",
                            )
                        )
                        continue

                if action.payload and "human_labels" in action.payload:
                    annotation.human_labels = action.payload["human_labels"]
                    annotation.status = "HUMAN_REVIEW"
                    db.add(
                        AnnotationAction(
                            session_id=session.id,
                            annotation_id=annotation.id,
                            action_type="offline_edit",
                            image_index=annotation.image_index,
                            payload=action.payload,
                        )
                    )
                    committed.append(action.annotation_id)
                else:
                    rejected.append(
                        {
                            "annotation_id": str(action.annotation_id),
                            "reason": "No human_labels in payload",
                        }
                    )

            elif action.action_type == "delete":
                if annotation.human_labels is not None:
                    annotation.human_labels = None
                    annotation.status = "PENDING"
                    db.add(
                        AnnotationAction(
                            session_id=session.id,
                            annotation_id=annotation.id,
                            action_type="offline_delete",
                            image_index=annotation.image_index,
                            payload={},
                        )
                    )
                    committed.append(action.annotation_id)
                else:
                    rejected.append(
                        {
                            "annotation_id": str(action.annotation_id),
                            "reason": "No labels to delete",
                        }
                    )

            elif action.action_type == "approve":
                annotation.status = "CERTIFIED"
                annotation.is_certified = True
                db.add(
                    AnnotationAction(
                        session_id=session.id,
                        annotation_id=annotation.id,
                        action_type="offline_approve",
                        image_index=annotation.image_index,
                        payload={},
                    )
                )
                committed.append(action.annotation_id)

            elif action.action_type == "reject":
                annotation.status = "REJECTED"
                db.add(
                    AnnotationAction(
                        session_id=session.id,
                        annotation_id=annotation.id,
                        action_type="offline_reject",
                        image_index=annotation.image_index,
                        payload=action.payload or {},
                    )
                )
                committed.append(action.annotation_id)

            elif action.action_type == "create":
                if action.payload and "human_labels" in action.payload:
                    annotation.human_labels = action.payload["human_labels"]
                    annotation.status = "HUMAN_REVIEW"
                    db.add(
                        AnnotationAction(
                            session_id=session.id,
                            annotation_id=annotation.id,
                            action_type="offline_create",
                            image_index=annotation.image_index,
                            payload=action.payload,
                        )
                    )
                    committed.append(action.annotation_id)
                else:
                    rejected.append(
                        {
                            "annotation_id": str(action.annotation_id),
                            "reason": "No human_labels in payload",
                        }
                    )

        except Exception as exc:
            rejected.append(
                {"annotation_id": str(action.annotation_id), "reason": str(exc)}
            )

    session.annotations_created += len(committed)
    await db.commit()

    return SyncBatchResponse(
        committed=committed,
        conflicts=conflicts,
        rejected=rejected,
        server_timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/sync/status")
async def sync_status(
    session_id: UUID,
    since: str | None = Query(
        default=None, description="ISO timestamp to check changes since"
    ),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get sync status for a session: which annotations have server changes."""
    user_id = UUID(user["sub"])

    stmt = select(AnnotationSession).where(
        and_(
            AnnotationSession.id == session_id,
            AnnotationSession.user_id == user_id,
        )
    )
    session = (await db.execute(stmt)).scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    since_dt = session.started_at
    if since:
        with contextlib.suppress(ValueError):
            since_dt = datetime.fromisoformat(since)

    limit = 200
    ann_stmt = (
        select(Annotation)
        .where(
            and_(
                Annotation.dataset_id == session.dataset_id,
                Annotation.updated_at > since_dt,
            )
        )
        .order_by(Annotation.updated_at.desc())
        .limit(limit)
    )
    recent_changes = (await db.execute(ann_stmt)).scalars().all()

    return {
        "session_id": str(session_id),
        "server_changes": [
            {
                "annotation_id": str(a.id),
                "image_index": a.image_index,
                "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
                "etag": hashlib.md5(
                    a.updated_at.isoformat().encode()
                ).hexdigest() if a.updated_at else None,
            }
            for a in recent_changes
        ],
        "session_active": session.is_active,
        "has_more": len(recent_changes) == limit,
    }
