from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import model_inference
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.logging import get_logger
from app.models.deployed_model import DeployedModel
from app.models.enums import ModelType, TrainingStatus
from app.models.training import TrainingJob
from app.schemas.model_registry import (
    DeployedModelListResponse,
    DeployedModelResponse,
    DeployModelRequest,
)

logger = get_logger("edgevision.model_registry")

model_registry_router = APIRouter(prefix="/studio/models", tags=["Model Registry"])


def _map_model(m: DeployedModel) -> DeployedModelResponse:
    return DeployedModelResponse(
        id=m.id,
        training_job_id=m.training_job_id,
        model_name=m.model_name,
        model_type=m.model_type,
        version=m.version,
        dataset_id=m.dataset_id,
        artifact_path=m.artifact_path,
        accuracy=m.accuracy,
        is_active=m.is_active,
        deployed_by=m.deployed_by,
        deployed_at=m.deployed_at,
        notes=m.notes,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


@model_registry_router.get("/", response_model=DeployedModelListResponse)
async def list_models(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    model_type: ModelType | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DeployedModel)
    if model_type is not None:
        stmt = stmt.where(DeployedModel.model_type == model_type)
    if is_active is not None:
        stmt = stmt.where(DeployedModel.is_active == is_active)
    stmt = stmt.order_by(DeployedModel.model_type, DeployedModel.created_at.desc())

    all_rows = (await db.execute(stmt)).scalars().all()
    total = len(all_rows)
    offset = (page - 1) * page_size
    rows = (await db.execute(stmt.offset(offset).limit(page_size))).scalars().all()

    return DeployedModelListResponse.create([_map_model(m) for m in rows], total, page, page_size)


@model_registry_router.post("/deploy", response_model=DeployedModelResponse, status_code=status.HTTP_201_CREATED)
async def deploy_model(
    body: DeployModelRequest,
    user: dict = Depends(require_role(["ADMIN", "OPERATOR"])),
    db: AsyncSession = Depends(get_db),
):
    """Promote a completed training job's artifact into the model registry.

    Creates a new, inactive DeployedModel entry. Use POST /{model_id}/activate
    to make it the live model for its model_type.
    """
    job = await db.get(TrainingJob, body.training_job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training job not found")

    if job.status != TrainingStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only completed training jobs can be deployed to the model registry",
        )

    if not job.artifact_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Training job has no artifact to deploy",
        )

    existing_count = (
        await db.execute(select(func.count(DeployedModel.id)).where(DeployedModel.model_type == job.model_type))
    ).scalar_one()
    version = f"v{existing_count + 1}"

    deployed = DeployedModel(
        training_job_id=job.id,
        model_name=job.model_name,
        model_type=job.model_type,
        version=version,
        dataset_id=job.dataset_id,
        artifact_path=job.artifact_path,
        accuracy=job.accuracy,
        is_active=False,
        notes=body.notes,
    )
    db.add(deployed)
    await db.commit()
    await db.refresh(deployed)

    logger.info(
        "model_deployed",
        deployed_model_id=str(deployed.id),
        training_job_id=str(job.id),
        model_type=job.model_type.value,
        version=version,
    )

    return _map_model(deployed)


@model_registry_router.post("/{model_id}/activate", response_model=DeployedModelResponse)
async def activate_model(
    model_id: UUID,
    user: dict = Depends(require_role(["ADMIN", "OPERATOR"])),
    db: AsyncSession = Depends(get_db),
):
    """Make a deployed model the active one for its model_type.

    Deactivates every other DeployedModel of the same model_type and clears
    the in-process inference cache so the next request loads this artifact.
    """
    target = await db.get(DeployedModel, model_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployed model not found")

    result = await db.execute(
        select(DeployedModel).where(DeployedModel.model_type == target.model_type).with_for_update()
    )
    siblings = result.scalars().all()
    for m in siblings:
        m.is_active = m.id == target.id

    target.deployed_by = UUID(user["sub"])
    target.deployed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(target)

    model_inference.clear_cache()

    logger.info(
        "model_activated",
        deployed_model_id=str(target.id),
        model_type=target.model_type.value,
        version=target.version,
    )

    return _map_model(target)


@model_registry_router.get("/{model_id}", response_model=DeployedModelResponse)
async def get_model_detail(
    model_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    m = await db.get(DeployedModel, model_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployed model not found")
    return _map_model(m)
