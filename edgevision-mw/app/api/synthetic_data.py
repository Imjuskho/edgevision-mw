from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.features import require_role_and_feature
from app.schemas.synthetic_data import (
    SyntheticJobCreate,
    SyntheticJobResponse,
    SyntheticJobListResponse,
    SyntheticFrameResponse,
    SyntheticValidationResponse,
)

router = APIRouter(prefix="/synthetic", tags=["Synthetic Data"])


@router.post("/generate", response_model=SyntheticJobResponse)
async def start_generation(
    request: SyntheticJobCreate,
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR"], "syntheticData")),
):
    from app.services.synthetic_data import create_generation_job
    from app.core.database import get_db

    async for db in get_db():
        job = await create_generation_job(db, request.dataset_id, request.target_count, request.config)
        return SyntheticJobResponse.model_validate(job)
    raise HTTPException(status_code=500, detail="DB unavailable")


@router.get("/jobs", response_model=SyntheticJobListResponse)
async def list_jobs(user: dict = Depends(get_current_user)):
    from app.services.synthetic_data import get_synthetic_datasets
    from app.core.database import get_db

    async for db in get_db():
        jobs = await get_synthetic_datasets(db)
        return SyntheticJobListResponse(
            items=[SyntheticJobResponse(**j) for j in jobs],
            total=len(jobs),
        )
    raise HTTPException(status_code=500, detail="DB unavailable")


@router.get("/jobs/{job_id}", response_model=SyntheticJobResponse)
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    from app.services.synthetic_data import get_generation_status
    from app.core.database import get_db

    async for db in get_db():
        status = await get_generation_status(db, job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return SyntheticJobResponse(**status)
    raise HTTPException(status_code=500, detail="DB unavailable")


@router.post("/jobs/{job_id}/validate")
async def validate_job(
    job_id: str,
    user: dict = Depends(require_role_and_feature(["ADMIN", "OPERATOR"], "syntheticData")),
):
    from app.services.synthetic_data import validate_real_vs_synthetic
    from app.core.database import get_db

    async for db in get_db():
        return await validate_real_vs_synthetic(db, job_id)
    raise HTTPException(status_code=500, detail="DB unavailable")


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    user: dict = Depends(require_role_and_feature(["ADMIN"], "syntheticData")),
):
    from app.services.synthetic_data import delete_generation_job
    from app.core.database import get_db

    async for db in get_db():
        await delete_generation_job(db, job_id)
        return {"status": "deleted", "job_id": job_id}
    raise HTTPException(status_code=500, detail="DB unavailable")
