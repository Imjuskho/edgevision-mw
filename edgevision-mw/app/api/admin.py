from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_inference import clear_cache, get_active_deployed_model, get_lkg_status
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.deployed_model import DeployedModel
from app.models.enums import ModelType

admin_router = APIRouter(tags=["Admin"], prefix="/admin")


@admin_router.get("/lkg-status")
async def lkg_status(
    user: dict = Depends(require_role(["ADMIN"])),
):
    return {
        "last_known_good": get_lkg_status(),
    }


@admin_router.post("/models/rollback")
async def rollback_model(
    model_type: ModelType,
    target_deployed_model_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role(["ADMIN"])),
):
    target = await db.execute(
        select(DeployedModel).where(
            DeployedModel.id == target_deployed_model_id,
            DeployedModel.model_type == model_type,
        )
    )
    target_model = target.scalar_one_or_none()
    if target_model is None:
        raise HTTPException(status_code=404, detail="Target deployed model not found")

    current = await get_active_deployed_model(db, model_type)
    if current is not None:
        current.is_active = False

    target_model.is_active = True
    await db.commit()

    clear_cache()

    return {
        "status": "ok",
        "message": f"Rolled back {model_type.value} to version {target_model.version} ({target_model.model_name})",
    }
