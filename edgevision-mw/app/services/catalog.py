from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import AnnotationStatus, DatasetStatus, LicenseType
from app.schemas.catalog import (
    DatasetManifest,
    DatasetResponse,
    QuoteResponse,
)
from app.schemas.common import PaginatedResponse

EXCLUSIVITY_MULTIPLIERS = {
    "ANNUAL": Decimal("1.0"),
    "PERPETUAL": Decimal("1.5"),
    "EXCLUSIVE": Decimal("2.5"),
}
GEOGRAPHY_PREMIUMS = {
    "MW": Decimal("1.0"),
    "US": Decimal("1.3"),
    "GB": Decimal("1.3"),
    "EU": Decimal("1.2"),
    "DEFAULT": Decimal("1.1"),
}
BASE_PRICE_PER_IMAGE = Decimal("0.30")


async def search_datasets(
    db: AsyncSession, filters: dict | None = None, page: int = 1, page_size: int = 50
) -> PaginatedResponse:
    query = select(Dataset)
    count_query = select(func.count()).select_from(Dataset)
    conditions = []

    if filters:
        if filters.get("status"):
            conditions.append(Dataset.status == filters["status"])
        if filters.get("license_type"):
            conditions.append(Dataset.license_type == filters["license_type"])
        if filters.get("min_samples"):
            conditions.append(Dataset.sample_count >= filters["min_samples"])
        if filters.get("search"):
            search_term = f"%{filters['search']}%"
            conditions.append(Dataset.name.ilike(search_term))
    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Dataset.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    datasets = result.scalars().all()

    items = [
        DatasetResponse(
            id=d.id,
            dataset_id=d.dataset_id,
            name=d.name,
            version=d.version,
            status=d.status.value if hasattr(d.status, "value") else d.status,
            sample_count=d.sample_count,
            classes=d.classes,
            annotations_per_image=d.annotations_per_image,
            image_width=d.image_width,
            image_height=d.image_height,
            geographic_coverage=d.geographic_coverage,
            demographic_report=d.demographic_report,
            consent_coverage_pct=d.consent_coverage_pct,
            pii_scrub_verified=d.pii_scrub_verified,
            iaa_score=d.iaa_score,
            formats=d.formats,
            price_usd=d.price_usd,
            license_type=d.license_type.value if hasattr(d.license_type, "value") else d.license_type,
            created_at=d.created_at,
        )
        for d in datasets
    ]

    return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)


async def trigger_build(db: AsyncSession, build_request: dict) -> DatasetResponse:
    # Create dataset record with BUILDING status
    dataset_id_str = f"ds-{uuid4().hex[:12]}"

    dataset = Dataset(
        id=uuid4(),
        dataset_id=dataset_id_str,
        name=build_request["name"],
        version="1.0.0",
        status=DatasetStatus.BUILDING,
        sample_count=0,  # Will be updated by Celery task
        classes={},
        annotations_per_image=0.0,
        image_width=1920,
        image_height=1080,
        geographic_coverage={"countries": ["MW"]},
        demographic_report={},
        consent_coverage_pct=0.0,
        pii_scrub_verified=False,
        iaa_score=0.0,
        formats=build_request.get("formats", ["COCO", "YOLO"]),
        price_usd=Decimal("0.00"),
        license_type=LicenseType(build_request.get("license_type", "ANNUAL")),
    )
    db.add(dataset)
    await db.commit()
    await db.refresh(dataset)

    # Dispatch Celery task for background build
    import json

    from app.workers.tasks import build_dataset_task
    build_dataset_task.delay(
        dataset_id=str(dataset.id),
        build_request_json=json.dumps(build_request),
    )

    return DatasetResponse(
        id=dataset.id,
        dataset_id=dataset.dataset_id,
        name=dataset.name,
        version=dataset.version,
        status=dataset.status.value if hasattr(dataset.status, 'value') else dataset.status,
        sample_count=0,
        classes={},
        annotations_per_image=0.0,
        image_width=1920,
        image_height=1080,
        geographic_coverage={"countries": ["MW"]},
        demographic_report={},
        consent_coverage_pct=0.0,
        pii_scrub_verified=False,
        iaa_score=0.0,
        formats=dataset.formats,
        price_usd=Decimal("0.00"),
        license_type=dataset.license_type.value if hasattr(dataset.license_type, 'value') else dataset.license_type,
        created_at=dataset.created_at,
    )


async def build_dataset_sync(db: AsyncSession, dataset_id: str, build_request: dict) -> bool:
    """Synchronous dataset build called by Celery worker."""
    import json

    result = await db.execute(select(Dataset).where(Dataset.id == UUID(dataset_id)))
    dataset = result.scalar_one_or_none()
    if dataset is None:
        return False

    annotation_ids = [UUID(aid) for aid in json.loads(build_request).get("annotation_ids", [])]
    result = await db.execute(
        select(Annotation).where(
            Annotation.id.in_(annotation_ids),
            Annotation.status == AnnotationStatus.CERTIFIED,
        )
    )
    certified = result.scalars().all()
    if not certified:
        dataset.status = DatasetStatus.RETRACTED
        await db.commit()
        return False

    # Stratified sampling by class
    class_counts: dict[str, list] = {}
    for ann in certified:
        labels = ann.auto_labels or ann.human_labels or {}
        classes = labels.get("classes", ["unknown"])
        for cls in classes:
            class_counts.setdefault(cls, []).append(ann)

    # Balance classes - take equal number from each
    min_count = min(len(v) for v in class_counts.values()) if class_counts else 0
    balanced = []
    for cls, anns in class_counts.items():
        balanced.extend(anns[:min_count])

    # Deduplicate
    seen_ids = set()
    deduped = []
    for ann in balanced:
        if ann.id not in seen_ids:
            seen_ids.add(ann.id)
            deduped.append(ann)

    # Calculate stats
    classes_dict = {}
    for ann in deduped:
        labels = ann.auto_labels or ann.human_labels or {}
        for cls in labels.get("classes", ["unknown"]):
            classes_dict[cls] = classes_dict.get(cls, 0) + 1

    avg_iaa = sum(a.iaa_score or 0 for a in deduped) / max(len(deduped), 1)

    # Run PII check
    from app.services.compliance import run_pii_check
    pii_result = await run_pii_check(db, dataset.dataset_id)

    # Update dataset
    dataset.sample_count = len(deduped)
    dataset.classes = classes_dict
    dataset.iaa_score = round(avg_iaa, 4)
    dataset.consent_coverage_pct = 100.0
    dataset.pii_scrub_verified = pii_result.passed
    dataset.status = DatasetStatus.READY

    # Calculate price
    price = calculate_price({
        "sample_count": len(deduped),
        "license_type": dataset.license_type.value if hasattr(dataset.license_type, 'value') else dataset.license_type,
        "complexity": 1.0,
    })
    dataset.price_usd = price

    await db.commit()
    return True


async def get_manifest(db: AsyncSession, dataset_id: str) -> DatasetManifest | None:
    from app.models.annotation import Annotation

    result = await db.execute(
        select(Dataset).where(Dataset.dataset_id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        return None

    class_names = list(dataset.classes.keys())
    category_ids: dict[str, int] = {
        name: idx + 1 for idx, name in enumerate(class_names)
    }

    ann_result = await db.execute(
        select(Annotation).where(Annotation.dataset_id == dataset.id)
    )
    annotations = ann_result.scalars().all()

    images: list[dict] = []
    manifest_annotations: list[dict] = []

    annotation_id = 1
    for image_id, ann in enumerate(annotations, start=1):
        images.append(
            {
                "id": image_id,
                "file_name": ann.image_path.rsplit("/", 1)[-1],
                "width": dataset.image_width or 0,
                "height": dataset.image_height or 0,
            }
        )

        objects = ann.detected_objects or {}
        if isinstance(objects, dict):
            objects = objects.get("objects", [])
        if not isinstance(objects, list):
            objects = []

        for obj in objects:
            if not isinstance(obj, dict):
                continue
            class_name = obj.get("class_name") or obj.get("class")
            if class_name not in category_ids:
                continue
            bbox = obj.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                continue
            x, y, w, h = bbox[0], bbox[1], bbox[2], bbox[3]
            manifest_annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": category_ids[class_name],
                    "bbox": [float(x), float(y), float(w), float(h)],
                    "area": float(w) * float(h),
                    "iscrowd": 0,
                    "confidence": float(obj.get("confidence", 1.0)),
                }
            )
            annotation_id += 1

    return DatasetManifest(
        dataset_id=dataset.dataset_id,
        format="COCO",
        info={
            "description": dataset.name,
            "version": dataset.version,
            "year": dataset.created_at.year,
        },
        images=images,
        annotations=manifest_annotations,
        categories=[
            {"id": category_ids[name], "name": name, "supercategory": "object"}
            for name in class_names
        ],
    )


async def generate_quote(db: AsyncSession, quote_request: dict) -> QuoteResponse:
    from app.models.quote import Quote

    result = await db.execute(
        select(Dataset).where(Dataset.dataset_id == quote_request["dataset_id"])
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise ValueError("Dataset not found")

    ds_status = dataset.status.value if hasattr(dataset.status, 'value') else dataset.status
    if ds_status != "FOR_SALE":
        raise ValueError(f"Dataset status is {ds_status}, expected FOR_SALE")

    base_price = dataset.price_usd
    license_type = quote_request.get("license_type", "ANNUAL")
    jurisdiction = quote_request.get("jurisdiction", "MW")
    buyer_id = quote_request.get("buyer_id")

    exclusivity_mult = EXCLUSIVITY_MULTIPLIERS.get(license_type, Decimal("1.0"))
    geo_premium = GEOGRAPHY_PREMIUMS.get(jurisdiction, GEOGRAPHY_PREMIUMS["DEFAULT"])
    total = (base_price * exclusivity_mult * geo_premium).quantize(Decimal("0.01"))

    quote_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=30)

    quote = Quote(
        id=quote_id,
        buyer_id=UUID(buyer_id) if buyer_id else None,
        dataset_id=dataset.dataset_id,
        base_price_usd=base_price,
        exclusivity_multiplier=exclusivity_mult,
        geography_premium=geo_premium,
        total_price_usd=total,
        license_type=license_type,
        jurisdiction=jurisdiction,
        expires_at=expires_at,
    )
    db.add(quote)
    await db.commit()

    return QuoteResponse(
        id=quote_id,
        dataset_id=dataset.dataset_id,
        base_price_usd=base_price,
        exclusivity_multiplier=exclusivity_mult,
        geography_premium=geo_premium,
        total_price_usd=total,
        license_type=license_type,
        expires_at=expires_at,
    )


def calculate_price(spec: dict) -> Decimal:
    sample_count = spec.get("sample_count", 0)
    license_type = spec.get("license_type", "ANNUAL")
    complexity = spec.get("complexity", 1.0)
    geography = spec.get("geography", "MW")

    base = Decimal(str(sample_count)) * Decimal(str(complexity)) * BASE_PRICE_PER_IMAGE

    geo_mult = GEOGRAPHY_PREMIUMS.get(geography, GEOGRAPHY_PREMIUMS["DEFAULT"])
    exclusivity_mult = EXCLUSIVITY_MULTIPLIERS.get(license_type, Decimal("1.0"))

    total = base * geo_mult * exclusivity_mult
    return total.quantize(Decimal("0.01"))


async def publish_dataset(
    db: AsyncSession, dataset_id: str
) -> DatasetResponse:
    """Transition a READY dataset to FOR_SALE (H4)."""
    result = await db.execute(
        select(Dataset).where(Dataset.dataset_id == dataset_id).with_for_update()
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise ValueError(f"Dataset {dataset_id} not found")

    current = dataset.status.value if hasattr(dataset.status, "value") else dataset.status
    if current != DatasetStatus.READY.value:
        raise ValueError(
            f"Cannot publish dataset in {current} status; expected {DatasetStatus.READY.value}"
        )

    dataset.status = DatasetStatus.FOR_SALE
    await db.commit()
    await db.refresh(dataset)

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
