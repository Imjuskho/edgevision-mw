from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_buyer_or_user, get_current_user, require_role
from app.schemas.catalog import (
    DatasetBuildRequest,
    DatasetManifest,
    DatasetResponse,
    QuoteRequest,
    QuoteResponse,
)
from app.services.catalog import (
    generate_quote,
    get_manifest,
    search_datasets,
    trigger_build,
)

catalog_router = APIRouter(prefix="/datasets", tags=["Catalog"])


@catalog_router.get("/")
async def list_datasets(
    search: str | None = Query(default=None, description="Search by name"),
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status"),
    license_type: str | None = Query(default=None, description="Filter by license type"),
    min_samples: int | None = Query(default=None, description="Minimum sample count"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(get_current_buyer_or_user),
    db: AsyncSession = Depends(get_db),
):
    filters = {}
    if search:
        filters["search"] = search
    if status_filter:
        filters["status"] = status_filter
    if license_type:
        filters["license_type"] = license_type
    if min_samples:
        filters["min_samples"] = min_samples
    return await search_datasets(db, filters or None, page, page_size)


@catalog_router.post(
    "/build",
    response_model=DatasetResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def build_dataset(
    body: DatasetBuildRequest,
    user: dict = Depends(require_role(["ADMIN", "OPERATOR"])),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await trigger_build(db, body.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@catalog_router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.models.dataset import Dataset

    result = await db.execute(select(Dataset).where(Dataset.dataset_id == dataset_id))
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found",
        )
    return DatasetResponse(
        id=dataset.id,
        dataset_id=dataset.dataset_id,
        name=dataset.name,
        version=dataset.version,
        status=dataset.status.value if hasattr(dataset.status, "value") else dataset.status,
        sample_count=dataset.sample_count,
        classes=dataset.classes,
        annotations_per_image=dataset.annotations_per_image,
        image_width=dataset.image_width,
        image_height=dataset.image_height,
        geographic_coverage=dataset.geographic_coverage,
        demographic_report=dataset.demographic_report,
        consent_coverage_pct=dataset.consent_coverage_pct,
        pii_scrub_verified=dataset.pii_scrub_verified,
        iaa_score=dataset.iaa_score,
        formats=dataset.formats,
        price_usd=dataset.price_usd,
        license_type=dataset.license_type.value if hasattr(dataset.license_type, "value") else dataset.license_type,
        created_at=dataset.created_at,
    )


@catalog_router.get("/{dataset_id}/manifest", response_model=DatasetManifest)
async def dataset_manifest(
    dataset_id: str,
    user: dict = Depends(get_current_buyer_or_user),
    db: AsyncSession = Depends(get_db),
):
    manifest = await get_manifest(db, dataset_id)
    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found",
        )
    return manifest


@catalog_router.post(
    "/quotes",
    response_model=QuoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_quote(
    body: QuoteRequest,
    user: dict = Depends(get_current_buyer_or_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        quote_data = body.model_dump()
        quote_data["buyer_id"] = user.get("sub")
        return await generate_quote(db, quote_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@catalog_router.get("/quotes/{quote_id}")
async def get_quote(
    quote_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.models.quote import Quote

    buyer_id = UUID(user["sub"])
    result = await db.execute(
        select(Quote).where(Quote.id == quote_id, Quote.buyer_id == buyer_id)
    )
    quote = result.scalar_one_or_none()
    if quote is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )
    return {
        "id": str(quote.id),
        "dataset_id": quote.dataset_id,
        "base_price_usd": quote.base_price_usd,
        "exclusivity_multiplier": quote.exclusivity_multiplier,
        "geography_premium": quote.geography_premium,
        "total_price_usd": quote.total_price_usd,
        "license_type": quote.license_type,
        "jurisdiction": quote.jurisdiction,
        "expires_at": quote.expires_at.isoformat(),
        "accepted_at": quote.accepted_at.isoformat() if quote.accepted_at else None,
    }
