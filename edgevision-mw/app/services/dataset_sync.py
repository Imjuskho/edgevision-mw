"""Bridge ImageRecord rows into studio Annotation rows and keep sample_count accurate."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.enums import AnnotationStatus, BatchStatus
from app.models.image import ImageRecord
from app.models.ingestion import IngestionBatch
from app.models.node import Node


async def _get_or_create_studio_node(db: AsyncSession) -> Node:
    from app.models.enums import NodeCategory, NodeStatus, PIIMode

    stmt = select(Node).where(Node.node_id == "studio-node").limit(1)
    node = (await db.execute(stmt)).scalar_one_or_none()
    if node is not None:
        return node

    node = Node(
        node_id="studio-node",
        district="Studio",
        latitude=0.0,
        longitude=0.0,
        category=NodeCategory.ROAD,
        hardware_profile={"type": "studio"},
        network_config={},
        capture_schedule="manual",
        interest_classes=[],
        pii_mode=PIIMode.MODERATE,
        firmware_version="1.0.0",
        public_key=b"\x00" * 32,
        status=NodeStatus.ONLINE,
        is_enabled=True,
    )
    db.add(node)
    await db.flush()
    return node


async def _get_or_create_studio_batch(db: AsyncSession, ds: Dataset) -> IngestionBatch:
    stmt = select(IngestionBatch).where(IngestionBatch.batch_id.startswith(f"STUDIO-{ds.dataset_id}")).limit(1)
    batch = (await db.execute(stmt)).scalar_one_or_none()
    if batch is not None:
        return batch

    node = await _get_or_create_studio_node(db)
    batch = IngestionBatch(
        batch_id=f"STUDIO-{ds.dataset_id}-{uuid4().hex[:8]}",
        node_id=node.id,
        hub_id="studio-hub",
        event_count=0,
        file_size_bytes=0,
        checksum_sha256="",
        node_signature=b"\x00" * 64,
        compression_codec="none",
        status=BatchStatus.INGESTED,
        quality_scores={},
    )
    db.add(batch)
    await db.flush()
    return batch


async def sync_image_records_to_annotations(db: AsyncSession, ds: Dataset) -> int:
    """Create Annotation rows for ImageRecords not yet linked to this dataset."""
    batch = await _get_or_create_studio_batch(db, ds)

    existing_paths = set(
        (await db.execute(select(Annotation.image_path).where(Annotation.dataset_id == ds.id))).scalars().all()
    )

    records = (
        (
            await db.execute(
                select(ImageRecord)
                .where(ImageRecord.dataset_id == ds.id)
                .order_by(ImageRecord.created_at.asc(), ImageRecord.id.asc())
            )
        )
        .scalars()
        .all()
    )

    max_image_index = (
        await db.execute(select(func.max(Annotation.image_index)).where(Annotation.dataset_id == ds.id))
    ).scalar()
    next_index = (max_image_index if max_image_index is not None else -1) + 1

    created = 0
    for record in records:
        if record.storage_key in existing_paths:
            continue
        db.add(
            Annotation(
                id=uuid4(),
                batch_id=batch.id,
                image_index=next_index,
                image_path=record.storage_key,
                thumbnail_path=record.thumbnail_key or record.storage_key,
                detected_objects={"objects": [], "_checksum": record.checksum_sha256 or ""},
                auto_labels={"labels": [], "source": record.source or "file"},
                status=AnnotationStatus.PENDING,
                quality_score=0.0,
                dataset_id=ds.id,
            )
        )
        existing_paths.add(record.storage_key)
        next_index += 1
        created += 1

    if created:
        await db.flush()
    return created


async def refresh_dataset_sample_count(db: AsyncSession, ds: Dataset) -> int:
    await db.flush()
    total = (await db.execute(select(func.count()).where(Annotation.dataset_id == ds.id))).scalar() or 0
    ds.sample_count = total
    await db.flush()
    return total


async def resolve_dataset(db: AsyncSession, identifier: str) -> Dataset | None:
    try:
        uid = UUID(identifier)
        ds = await db.get(Dataset, uid)
        if ds is not None:
            return ds
    except ValueError:
        pass
    return (await db.execute(select(Dataset).where(Dataset.dataset_id == identifier).limit(1))).scalar_one_or_none()


async def sync_dataset_pipeline(db: AsyncSession, ds: Dataset) -> int:
    """Sync image records → annotations and update sample_count. Returns image total."""
    await sync_image_records_to_annotations(db, ds)
    return await refresh_dataset_sample_count(db, ds)


async def sync_dataset_by_identifier(db: AsyncSession, identifier: str) -> Dataset | None:
    ds = await resolve_dataset(db, identifier)
    if ds is None:
        return None
    await sync_dataset_pipeline(db, ds)
    return ds
