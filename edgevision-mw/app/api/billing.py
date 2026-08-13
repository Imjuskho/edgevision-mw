from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_buyer_or_user, get_current_user, require_role
from app.models.enums import ExportStatus
from app.models.export import Export
from app.schemas.billing import (
    ExportRequest,
    ExportResponse,
    InferenceUsageResponse,
    RevenueBreakdown,
)
from app.services.billing import (
    confirm_delivery,
    get_revenue_breakdown,
    initiate_export,
)

billing_router = APIRouter(tags=["Billing"])


@billing_router.post(
    "/exports",
    response_model=ExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_export(
    body: ExportRequest,
    user: dict = Depends(require_role(["BUYER", "ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    export_data = body.model_dump()
    export_data["buyer_id"] = user["sub"]
    return await initiate_export(db, export_data)


@billing_router.get("/exports")
async def list_exports(
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    offset: int = Query(default=0, ge=0, description="Results offset"),
    user: dict = Depends(get_current_buyer_or_user),
    db: AsyncSession = Depends(get_db),
):
    buyer_id = UUID(user["sub"])
    query = select(Export).where(Export.buyer_id == buyer_id)
    if status_filter:
        query = query.where(Export.status == ExportStatus(status_filter))
    query = query.order_by(Export.initiated_at.desc()).offset(offset).limit(limit)

    count_query = select(func.count()).select_from(Export).where(Export.buyer_id == buyer_id)
    if status_filter:
        count_query = count_query.where(Export.status == ExportStatus(status_filter))

    result = await db.execute(query)
    exports = result.scalars().all()

    count_result = await db.execute(count_query)
    count = count_result.scalar()

    return {
        "exports": [ExportResponse.model_validate(e) for e in exports],
        "count": count or 0,
        "limit": limit,
        "offset": offset,
    }


@billing_router.get("/exports/{export_id}", response_model=ExportResponse)
async def get_export(
    export_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Export).where(Export.id == export_id))
    export = result.scalar_one_or_none()
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return ExportResponse.model_validate(export)


@billing_router.get("/billing/revenue", response_model=RevenueBreakdown)
async def revenue(
    period: str | None = Query(default=None, description="Billing period YYYY-MM"),
    user: dict = Depends(require_role(["ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    return await get_revenue_breakdown(db, period)


@billing_router.get("/billing/inference-usage")
async def inference_usage(
    period: str | None = Query(default=None, description="Billing period YYYY-MM"),
    user: dict = Depends(get_current_buyer_or_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func as sa_func

    from app.models.inference_usage import InferenceUsage

    buyer_id = UUID(user["sub"])
    query = select(
        InferenceUsage.model_type,
        sa_func.sum(InferenceUsage.input_count),
        sa_func.sum(InferenceUsage.cost_usd),
    ).where(InferenceUsage.user_id == buyer_id)

    if period:
        query = query.where(
            func.to_char(InferenceUsage.billed_at, "YYYY-MM") == period
        )

    query = query.group_by(InferenceUsage.model_type)

    result = await db.execute(query)
    rows = result.all()

    return [
        InferenceUsageResponse(
            model_type=r[0].value if hasattr(r[0], "value") else str(r[0]),
            total_inputs=int(r[1]),
            total_cost_usd=r[2],
            period=period or "all",
        )
        for r in rows
    ]


@billing_router.post("/webhooks/buyer")
async def buyer_delivery_webhook(
    export_id: UUID = Query(...),
    delivered: bool = Query(default=True),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if delivered:
        success = await confirm_delivery(db, export_id)
        return {"confirmed": success, "export_id": str(export_id)}
    return {"confirmed": False, "export_id": str(export_id)}
