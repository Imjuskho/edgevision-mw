from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_node_auth
from app.schemas.ingestion import (
    BatchResponse,
    BatchUpload,
    IngestionQueue,
    ValidationResult,
)
from app.services.ingestion import (
    get_batch_detail,
    get_batches,
    get_queue_stats,
    receive_batch,
    validate_batch,
)

ingestion_router = APIRouter(prefix="/ingest", tags=["Ingestion"])


@ingestion_router.post("/batch", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def ingest_batch(
    batch: BatchUpload,
    file: bytes | None = None,
    node_auth: dict = Depends(require_node_auth),
    db: AsyncSession = Depends(get_db),
):
    batch_data = batch.model_dump()
    batch_data["node_signature"] = batch_data.get("node_signature", "")
    batch_data["hub_id"] = "edge-hub-01"
    response = await receive_batch(db, batch_data, file)
    return response


@ingestion_router.get("/queue", response_model=IngestionQueue)
async def queue_stats(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_queue_stats(db)


@ingestion_router.post("/validate", response_model=ValidationResult)
async def validate_upload(
    batch: BatchUpload,
    signature: str = Form(default=""),
    node_auth: dict = Depends(require_node_auth),
    db: AsyncSession = Depends(get_db),
):
    batch_data = batch.model_dump()
    return await validate_batch(db, batch_data, signature)


@ingestion_router.get("/batches")
async def list_batches(
    node_id: str | None = Query(default=None, description="Filter by node UUID"),
    batch_status: str | None = Query(default=None, alias="status", description="Filter by status"),
    start_date: datetime | None = Query(default=None, description="Start date filter"),
    end_date: datetime | None = Query(default=None, description="End date filter"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Results offset"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    batches = await get_batches(db, node_id, batch_status, start_date, end_date, limit, offset)
    return {"batches": batches, "count": len(batches)}


@ingestion_router.get("/batches/{batch_id}")
async def get_batch(
    batch_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    detail = await get_batch_detail(db, batch_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found",
        )
    return detail
