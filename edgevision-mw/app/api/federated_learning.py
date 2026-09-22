from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user, require_role
from app.core.features import require_role_and_feature
from app.schemas.federated_learning import (
    FLRoundCreate,
    FLRoundResponse,
    FLRoundListResponse,
    FLWeightUpdateSubmit,
    FLWeightUpdateResponse,
    FLOverviewResponse,
)

router = APIRouter(prefix="/fl", tags=["Federated Learning"])


@router.post("/rounds", response_model=FLRoundResponse)
async def create_round(
    request: FLRoundCreate,
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR"], "federatedLearning")),
):
    from app.services.federated_learning import create_sync_round
    from app.core.database import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    async for db in get_db():
        fl_round = await create_sync_round(
            db, request.model_type, target_contributors=request.target_contributors, noise_multiplier=request.noise_multiplier
        )
        return FLRoundResponse.model_validate(fl_round)
    raise HTTPException(status_code=500, detail="DB unavailable")


@router.get("/rounds", response_model=FLRoundListResponse)
async def list_rounds(user: dict = Depends(get_current_user)):
    from app.services.federated_learning import get_fl_overview
    from app.core.database import get_db
    from sqlalchemy import select
    from app.models.federated_learning import FLSyncRound

    async for db in get_db():
        result = await db.execute(select(FLSyncRound).order_by(FLSyncRound.created_at.desc()).limit(50))
        rounds = result.scalars().all()
        return FLRoundListResponse(
            items=[FLRoundResponse.model_validate(r) for r in rounds],
            total=len(rounds),
        )
    raise HTTPException(status_code=500, detail="DB unavailable")


@router.get("/rounds/{round_id}", response_model=FLRoundResponse)
async def get_round(round_id: str, user: dict = Depends(get_current_user)):
    from app.services.federated_learning import get_round_status
    from app.core.database import get_db

    async for db in get_db():
        status = await get_round_status(db, round_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Round not found")
        return status
    raise HTTPException(status_code=500, detail="DB unavailable")


@router.post("/rounds/{round_id}/aggregate")
async def aggregate_round(
    round_id: str,
    user: dict = Depends(require_role_and_feature(["ADMIN"], "federatedLearning")),
):
    from app.services.federated_learning import aggregate_weights
    from app.core.database import get_db

    async for db in get_db():
        result = await aggregate_weights(db, round_id)
        return result
    raise HTTPException(status_code=500, detail="DB unavailable")


@router.post("/weight-updates", response_model=FLWeightUpdateResponse)
async def submit_weight_update(request: FLWeightUpdateSubmit):
    from app.services.federated_learning import submit_weight_update
    from app.core.database import get_db

    async for db in get_db():
        update = await submit_weight_update(
            db, request.round_id, request.node_id, request.num_samples,
            request.local_loss, request.local_accuracy, request.artifact_path
        )
        return FLWeightUpdateResponse.model_validate(update)
    raise HTTPException(status_code=500, detail="DB unavailable")


@router.get("/overview", response_model=FLOverviewResponse)
async def overview(user: dict = Depends(get_current_user)):
    from app.services.federated_learning import get_fl_overview
    from app.core.database import get_db

    async for db in get_db():
        stats = await get_fl_overview(db)
        return FLOverviewResponse(**stats)
    raise HTTPException(status_code=500, detail="DB unavailable")
