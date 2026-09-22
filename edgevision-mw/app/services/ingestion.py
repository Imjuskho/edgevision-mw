from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import BatchStatus
from app.models.ingestion import IngestionBatch
from app.schemas.ingestion import (
    BatchResponse,
    IngestionQueue,
    ValidationResult,
)

logger = get_logger("edgevision.ingestion")

MAX_BATCH_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB


async def receive_batch(db: AsyncSession, batch_data: dict, file: bytes | None = None) -> BatchResponse:
    batch_id = batch_data["batch_id"]

    # Idempotency: if batch_id already exists, return existing record
    existing = await db.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id))
    existing_batch = existing.scalar_one_or_none()
    if existing_batch is not None:
        return BatchResponse(
            id=existing_batch.id,
            batch_id=existing_batch.batch_id,
            status=existing_batch.status.value if hasattr(existing_batch.status, "value") else existing_batch.status,
            ingested_at=existing_batch.ingested_at,
            storage_path=existing_batch.storage_path,
            event_count=existing_batch.event_count,
        )

    # File size limit
    file_size = batch_data.get("file_size_bytes", 0)
    if file_size > MAX_BATCH_FILE_SIZE_BYTES:
        batch = IngestionBatch(
            id=uuid4(),
            batch_id=batch_id,
            node_id=batch_data["node_id"],
            hub_id=batch_data.get("hub_id", "default-hub"),
            event_count=batch_data.get("event_count", 0),
            file_size_bytes=file_size,
            checksum_sha256=batch_data.get("checksum_sha256", ""),
            node_signature=b"",
            compression_codec=batch_data.get("compression_codec", "h265"),
            status=BatchStatus.REJECTED,
            quality_scores={"rejection_reason": f"File size {file_size} exceeds max {MAX_BATCH_FILE_SIZE_BYTES} bytes"},
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)
        status_val = batch.status.value if hasattr(batch.status, "value") else batch.status
        return BatchResponse(
            id=batch.id,
            batch_id=batch.batch_id,
            status=status_val,
            ingested_at=batch.ingested_at,
            storage_path=batch.storage_path,
            event_count=batch.event_count,
        )

    # Checksum verification: if file bytes provided, verify SHA-256
    if file is not None:
        actual_hash = hashlib.sha256(file).hexdigest()
        expected_hash = batch_data.get("checksum_sha256", "")
        if actual_hash != expected_hash:
            batch = IngestionBatch(
                id=uuid4(),
                batch_id=batch_id,
                node_id=batch_data["node_id"],
                hub_id=batch_data.get("hub_id", "default-hub"),
                event_count=batch_data.get("event_count", 0),
                file_size_bytes=file_size,
                checksum_sha256=expected_hash,
                node_signature=b"",
                compression_codec=batch_data.get("compression_codec", "h265"),
                status=BatchStatus.REJECTED,
                quality_scores={"rejection_reason": f"Checksum mismatch: expected {expected_hash}, got {actual_hash}"},
            )
            db.add(batch)
            await db.commit()
            await db.refresh(batch)
            status_val = batch.status.value if hasattr(batch.status, "value") else batch.status
            return BatchResponse(
                id=batch.id,
                batch_id=batch.batch_id,
                status=status_val,
                ingested_at=batch.ingested_at,
                storage_path=batch.storage_path,
                event_count=batch.event_count,
            )

    batch = IngestionBatch(
        id=uuid4(),
        batch_id=batch_id,
        node_id=batch_data["node_id"],
        hub_id=batch_data.get("hub_id", "default-hub"),
        event_count=batch_data["event_count"],
        file_size_bytes=file_size,
        checksum_sha256=batch_data["checksum_sha256"],
        node_signature=base64.b64decode(batch_data.get("node_signature", ""))
        if batch_data.get("node_signature")
        else b"",
        compression_codec=batch_data.get("compression_codec", "h265"),
        status=BatchStatus.PENDING,
        quality_scores=batch_data.get("quality_scores", {}),
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    # Store file in MinIO if provided
    if file is not None:
        storage_path = f"raw/{batch.node_id}/{batch.batch_id}"
        try:
            from app.core.dependencies import get_minio_client

            minio_client = await get_minio_client()
            minio_client.put_object(
                settings.MINIO_BUCKET,
                storage_path,
                data=file,
                length=len(file),
                content_type="application/octet-stream",
            )
        except Exception:
            pass  # Log but don't fail — batch record is already persisted

    # Dispatch background processing so PENDING batches are not a dead end.
    # Non-blocking: a dispatch failure (e.g. broker down) should not fail the
    # HTTP response to the node — but it must be visible for ops alerting.
    try:
        from app.workers.tasks import auto_label_task

        auto_label_task.delay(str(batch.id))
    except Exception as exc:
        logger.error(
            "batch_dispatch_failed",
            batch_id=batch_id,
            node_id=batch_data["node_id"],
            error=str(exc),
        )
        from app.models.audit import AuditLog

        db.add(
            AuditLog(
                event_type="BATCH_DISPATCH_FAILED",
                severity="ERROR",
                resource_type="ingestion_batch",
                resource_id=batch.id,
                details={
                    "batch_id": batch_id,
                    "node_id": batch_data["node_id"],
                    "error": str(exc),
                },
                actor_type="SYSTEM",
            )
        )
        await db.commit()

    return BatchResponse(
        id=batch.id,
        batch_id=batch.batch_id,
        status=batch.status.value if hasattr(batch.status, "value") else batch.status,
        ingested_at=batch.ingested_at,
        storage_path=batch.storage_path,
        event_count=batch.event_count,
    )


async def validate_batch(db: AsyncSession, batch_data: dict, signature: str) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Verify checksum format
    import re

    checksum = batch_data.get("checksum_sha256", "")
    if not re.match(r"^[0-9a-fA-F]{64}$", checksum):
        errors.append("Invalid checksum format: must be 64-character hex string")

    # 2. Verify signature
    if signature:
        try:
            sig_bytes = base64.b64decode(signature)
            if len(sig_bytes) != 64:  # Ed25519 signatures are exactly 64 bytes
                errors.append(f"Invalid signature length: {len(sig_bytes)} bytes (expected 64)")
            else:
                # Get node's public key
                node_id = batch_data.get("node_id")
                if node_id:
                    from sqlalchemy import select as sel

                    from app.core.security import verify_node_signature
                    from app.models.node import Node

                    result = await db.execute(sel(Node).where(Node.id == UUID(node_id)))
                    node = result.scalar_one_or_none()
                    if node is None:
                        errors.append(f"Node {node_id} not found")
                    else:
                        message = f"{node_id}:{batch_data.get('timestamp', '')}".encode()
                        if not verify_node_signature(node.public_key, message, sig_bytes):
                            errors.append("Ed25519 signature verification failed")
        except Exception as e:
            errors.append(f"Signature parsing error: {e!s}")
    else:
        warnings.append("No signature provided - batch will be queued for manual review")

    # 3. Verify file size
    file_size = batch_data.get("file_size_bytes", 0)
    if file_size <= 0:
        errors.append("File size must be greater than 0")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


async def get_queue_stats(db: AsyncSession) -> IngestionQueue:
    pending = await db.execute(
        select(func.count()).select_from(IngestionBatch).where(IngestionBatch.status == BatchStatus.PENDING)
    )
    processing = await db.execute(
        select(func.count()).select_from(IngestionBatch).where(IngestionBatch.status == BatchStatus.VALIDATING)
    )
    completed = await db.execute(
        select(func.count()).select_from(IngestionBatch).where(IngestionBatch.status == BatchStatus.INGESTED)
    )

    oldest_result = await db.execute(
        select(IngestionBatch.created_at)
        .where(IngestionBatch.status == BatchStatus.PENDING)
        .order_by(IngestionBatch.created_at.asc())
        .limit(1)
    )
    oldest_pending = oldest_result.scalar_one_or_none()

    return IngestionQueue(
        total_pending=pending.scalar() or 0,
        total_processing=processing.scalar() or 0,
        total_completed=completed.scalar() or 0,
        avg_latency_seconds=0.0,
        oldest_pending=oldest_pending,
    )


async def process_batch(db: AsyncSession, batch_id: str) -> bool:
    result = await db.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id).with_for_update())
    batch = result.scalar_one_or_none()
    if batch is None:
        return False

    batch.status = BatchStatus.INGESTED
    batch.ingested_at = datetime.now(UTC)
    batch.storage_path = f"raw/{batch.node_id}/{batch.batch_id}"
    await db.commit()
    return True


async def get_batches(
    db: AsyncSession,
    node_id: str | None = None,
    batch_status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    query = select(IngestionBatch)
    conditions = []
    if node_id:
        conditions.append(IngestionBatch.node_id == UUID(node_id))
    if batch_status:
        conditions.append(IngestionBatch.status == batch_status)
    if start_date:
        conditions.append(IngestionBatch.created_at >= start_date)
    if end_date:
        conditions.append(IngestionBatch.created_at <= end_date)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(IngestionBatch.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    batches = result.scalars().all()
    return [
        {
            "id": str(b.id),
            "batch_id": b.batch_id,
            "node_id": str(b.node_id),
            "event_count": b.event_count,
            "status": b.status.value if hasattr(b.status, "value") else b.status,
            "created_at": b.created_at.isoformat(),
            "ingested_at": b.ingested_at.isoformat() if b.ingested_at else None,
        }
        for b in batches
    ]


async def get_batch_detail(db: AsyncSession, batch_id: str) -> dict | None:
    result = await db.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id))
    batch = result.scalar_one_or_none()
    if batch is None:
        return None
    return {
        "id": str(batch.id),
        "batch_id": batch.batch_id,
        "node_id": str(batch.node_id),
        "hub_id": batch.hub_id,
        "event_count": batch.event_count,
        "file_size_bytes": batch.file_size_bytes,
        "checksum_sha256": batch.checksum_sha256,
        "compression_codec": batch.compression_codec,
        "status": batch.status.value if hasattr(batch.status, "value") else batch.status,
        "storage_path": batch.storage_path,
        "quality_scores": batch.quality_scores,
        "created_at": batch.created_at.isoformat(),
        "ingested_at": batch.ingested_at.isoformat() if batch.ingested_at else None,
    }
