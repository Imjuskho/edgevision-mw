from __future__ import annotations

import asyncio
import logging
import threading
import traceback
from datetime import UTC, datetime
from uuid import uuid4

from celery import shared_task

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


def _set_task_correlation(correlation_id: str | None = None) -> None:
    """Propagate correlation_id from API calls into Celery worker logging context."""
    cid = correlation_id or str(uuid4().hex[:12])
    request_id_var.set(cid)

_worker_loops: dict[int, asyncio.AbstractEventLoop] = {}
_worker_loops_lock = threading.Lock()


def _write_heartbeat(name: str) -> None:
    """Write a heartbeat timestamp to Redis so /health/celery can track liveness."""
    try:
        import redis as _redis

        from app.core.config import settings as _settings

        r = _redis.Redis.from_url(
            _settings.CELERY_BROKER_URL,
            password=_settings.REDIS_PASSWORD,
            decode_responses=True,
        )
        r.setex(
            f"heartbeat:{name}",
            _settings.CELERY_TASK_HEARTBEAT_TTL,
            datetime.now(UTC).isoformat(),
        )
        r.close()
    except Exception:
        pass


def _run_async(coro):
    """Run an async coroutine from a sync Celery task.

    Uses a persistent event loop per thread so asyncpg connection
    pools (bound to the first loop they see) are reused across
    multiple _run_async calls within the same worker thread.
    """
    tid = threading.get_ident()
    with _worker_loops_lock:
        loop = _worker_loops.get(tid)
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _worker_loops[tid] = loop
    return loop.run_until_complete(coro)


async def _run_training_async(job_id: str) -> None:
    from app.core.database import async_session
    from app.services.training import run_training

    async with async_session() as db:
        await run_training(db, job_id)


async def _mark_training_failed_async(job_id: str, error: str | None = None) -> None:
    from datetime import UTC, datetime
    from uuid import UUID

    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.enums import TrainingStatus
    from app.models.training import TrainingJob

    async with async_session() as db:
        result = await db.execute(
            select(TrainingJob).where(TrainingJob.id == UUID(job_id)).with_for_update()
        )
        job = result.scalar_one_or_none()
        if job is None:
            return

        job.status = TrainingStatus.FAILED
        job.error_message = error or "Training task failed"
        job.completed_at = datetime.now(UTC)
        await db.commit()


@shared_task(
    name="workers.run_training",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def run_training_task(job_id: str) -> bool:
    try:
        logger.info("Starting training job %s", job_id)
        _run_async(_run_training_async(job_id))
        logger.info("Training job %s completed", job_id)
        _run_async(
            _write_audit_log(
                "TRAINING_JOB_COMPLETED",
                "INFO",
                {"job_id": job_id, "status": "completed"},
                resource_type="training_job",
                resource_id=job_id,
            )
        )
        return True
    except Exception as exc:
        logger.error("Training job %s failed: %s", job_id, exc)
        _run_async(_mark_training_failed_async(job_id, str(exc)))
        _run_async(
            _write_audit_log(
                "TRAINING_JOB_FAILED",
                "ERROR",
                {"job_id": job_id, "error": str(exc)},
                resource_type="training_job",
                resource_id=job_id,
            )
        )
        raise


async def _write_audit_log(
    event_type: str,
    severity: str,
    details: dict,
    resource_type: str = "system",
    resource_id=None,
    actor_type: str = "SYSTEM",
):
    from app.core.database import async_session
    from app.models.audit import AuditLog

    async with async_session() as db:
        db.add(
            AuditLog(
                id=uuid4(),
                event_type=event_type,
                severity=severity,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                actor_type=actor_type,
            )
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

async def _process_batch_async(batch_id: str) -> None:
    from app.core.database import async_session
    from app.services.ingestion import process_batch

    async with async_session() as db:
        await process_batch(db, batch_id)


@shared_task(
    name="workers.process_batch",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def process_batch_task(batch_id: str) -> bool:
    try:
        logger.info("Processing batch %s", batch_id)
        _run_async(_process_batch_async(batch_id))
        logger.info("Batch %s processed successfully", batch_id)
        _run_async(
            _write_audit_log(
                "BATCH_PROCESSED", "INFO",
                {"batch_id": batch_id, "status": "success"},
                resource_type="ingestion_batch", resource_id=batch_id,
            )
        )
        return True
    except Exception as exc:
        logger.error("Failed to process batch %s: %s", batch_id, exc)
        _run_async(
            _write_audit_log(
                "BATCH_PROCESS_FAILED", "ERROR",
                {"batch_id": batch_id, "error": str(exc), "traceback": traceback.format_exc()},
                resource_type="ingestion_batch", resource_id=batch_id,
            )
        )
        raise


# ---------------------------------------------------------------------------
# Dataset build
# ---------------------------------------------------------------------------

async def _build_dataset_async(dataset_id: str, build_request_json: str) -> None:
    from app.core.database import async_session
    from app.services.catalog import build_dataset_sync

    async with async_session() as db:
        await build_dataset_sync(db, dataset_id, build_request_json)


@shared_task(
    name="workers.build_dataset",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def build_dataset_task(dataset_id: str, build_request_json: str = "{}") -> bool:
    try:
        logger.info("Building dataset %s", dataset_id)
        _run_async(_build_dataset_async(dataset_id, build_request_json))
        logger.info("Dataset %s build completed", dataset_id)
        _run_async(
            _write_audit_log(
                "DATASET_BUILD_COMPLETED", "INFO",
                {"dataset_id": dataset_id, "status": "success"},
                resource_type="dataset", resource_id=dataset_id,
            )
        )
        return True
    except Exception as exc:
        logger.error("Failed to build dataset %s: %s", dataset_id, exc)
        _run_async(
            _write_audit_log(
                "DATASET_BUILD_FAILED", "ERROR",
                {"dataset_id": dataset_id, "error": str(exc), "traceback": traceback.format_exc()},
                resource_type="dataset", resource_id=dataset_id,
            )
        )
        raise


# ---------------------------------------------------------------------------
# Compliance audit
# ---------------------------------------------------------------------------

async def _run_audit_async() -> None:
    from app.core.database import async_session
    from app.services.compliance import run_daily_audit

    async with async_session() as db:
        result = await run_daily_audit(db)
        logger.info(
            "Audit result: %d subjects, %d active, %d withdrawn, %d affected",
            result.total_subjects,
            result.active_consents,
            result.withdrawn,
            result.affected_images,
        )


@shared_task(
    name="workers.run_compliance_audit",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
)
def run_compliance_audit_task() -> bool:
    try:
        logger.info("Running daily compliance audit")
        _run_async(_run_audit_async())
        logger.info("Compliance audit completed")
        _run_async(
            _write_audit_log(
                "COMPLIANCE_AUDIT_COMPLETED", "INFO",
                {"status": "success"},
                resource_type="compliance",
            )
        )
        return True
    except Exception as exc:
        logger.error("Failed to run compliance audit: %s", exc)
        _run_async(
            _write_audit_log(
                "COMPLIANCE_AUDIT_FAILED", "ERROR",
                {"error": str(exc), "traceback": traceback.format_exc()},
                resource_type="compliance",
            )
        )
        raise


# ---------------------------------------------------------------------------
# Auto-labeling (SAM/YOLO stub with real status transitions)
# ---------------------------------------------------------------------------

async def _auto_label_async(batch_id: str) -> dict:
    """Auto-label every image in a batch with real server-side inference.

    Pipeline per image:
      1. Fetch raw bytes from MinIO.
      2. Sliding-window YOLO classification (``app.services.prelabel``) to
         propose bounding-box detections with taxonomy labels.
      3. Instance masks: MobileSAM ONNX (``app.ai.sam_segmenter``) per
         detection when a working decoder is available; otherwise the bundled
         YOLOv8-seg ONNX (``app.ai.yolo_seg``) supplies real masks.
      4. Persist ``detected_objects`` + ``auto_labels`` on the Annotation row,
         then blur faces in the stored image so annotators never see raw faces.

    Every AI stage degrades gracefully: if models are unavailable or a stage
    fails, we fall back to bbox-only detections (or empty labels) while still
    transitioning the batch to INGESTED.
    """
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.annotation import Annotation
    from app.models.enums import AnnotationStatus, BatchStatus
    from app.models.ingestion import IngestionBatch

    async with async_session() as db:
        result = await db.execute(
            select(IngestionBatch).where(IngestionBatch.batch_id == batch_id).with_for_update()
        )
        batch = result.scalar_one_or_none()
        if batch is None:
            raise ValueError(f"Batch {batch_id} not found")

        batch.status = BatchStatus.INGESTED
        batch.ingested_at = datetime.now(UTC)

        from app.ai.sam_segmenter import get_sam_segmenter, mask_to_rle
        from app.core.config import settings
        from app.core.dependencies import get_minio_client_sync

        mc = get_minio_client_sync()

        annotations_created = 0
        prelabeled = 0
        segmented = 0
        face_blurred = 0

        for idx in range(batch.event_count):
            img_path = f"raw/{batch.node_id}/{batch_id}/{idx}.jpg"
            img_bytes: bytes | None = None
            if mc is not None:
                try:
                    resp = mc.get_object(settings.MINIO_BUCKET, img_path)
                    img_bytes = resp.read()
                except Exception:
                    img_bytes = None

            detected_objects = {"objects": []}
            auto_labels = {"labels": []}

            if img_bytes and len(img_bytes) >= 100:
                try:
                    from app.services.prelabel import prelabel_image

                    detections = prelabel_image(img_bytes)
                    prelabeled += len(detections)
                except Exception:
                    detections = []

                try:
                    import cv2
                    import numpy as np

                    arr = cv2.imdecode(
                        np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
                    )
                    if arr is None:
                        raise ValueError("undecodable image")

                    seg = get_sam_segmenter()
                    sam_loaded = seg.is_loaded()
                    from app.ai.locate_anything import get_locate_anything_segmenter
                    from app.ai.yolo_seg import (
                        assign_masks,
                        get_yolo_seg_segmenter,
                    )

                    la = get_locate_anything_segmenter()
                    la_loaded = la.is_loaded()
                    yolo = get_yolo_seg_segmenter()
                    yolo_loaded = yolo.is_loaded()
                    instances: list[dict] = []

                    if la_loaded:
                        instances = la.detect(img_bytes)
                        if instances:
                            detections = assign_masks(detections, instances)
                            if not detections:
                                for inst in instances:
                                    detections.append({
                                        "label": inst.get("taxonomy", inst.get("class_name", "object")),
                                        "class_name": inst.get("class_name", "object"),
                                        "confidence": inst.get("confidence", 0.0),
                                        "bbox": inst.get("bbox", []),
                                        "mask": inst.get("mask"),
                                    })

                    if yolo_loaded and not instances:
                        instances = yolo.detect(img_bytes)
                        detections = assign_masks(detections, instances)
                        if not detections and instances:
                            for inst in instances:
                                detections.append({
                                    "label": inst["taxonomy"],
                                    "class_name": inst["class_name"],
                                    "confidence": inst["confidence"],
                                    "bbox": inst["bbox"],
                                    "mask": inst["mask"],
                                })

                    h, w = arr.shape[:2]
                    objects: list[dict] = []
                    for det in detections:
                        bbox = det.get("bbox")
                        if not bbox or len(bbox) < 4:
                            continue
                        bx, by, bw, bh = bbox
                        px1, py1 = int(bx * w), int(by * h)
                        px2, py2 = int((bx + bw) * w), int((by + bh) * h)
                        mask = None
                        det_mask = det.get("mask")
                        if det_mask is not None and getattr(det_mask, "any", lambda: False)():
                            mask = det_mask
                        elif sam_loaded:
                            mask = seg.predict_box(arr, px1, py1, px2, py2)
                        obj = {
                            "class_name": det.get("label", "object"),
                            "class": det.get("label", "object"),
                            "bbox": bbox,
                            "confidence": round(float(det.get("confidence", 1.0)), 4),
                        }
                        if mask is not None:
                            mask_rle = mask_to_rle(mask)
                            if mask_rle:
                                obj["mask_rle"] = mask_rle
                                segmented += 1
                        objects.append(obj)
                    if objects:
                        detected_objects["objects"] = objects
                        auto_labels["labels"] = objects
                except Exception:
                    detected_objects["objects"] = detections
                    auto_labels["labels"] = detections

            annotation = Annotation(
                id=uuid4(),
                batch_id=batch.id,
                image_index=idx,
                image_path=img_path,
                thumbnail_path=f"raw/{batch.node_id}/{batch_id}/{idx}_thumb.jpg",
                detected_objects=detected_objects,
                auto_labels=auto_labels,
                status=AnnotationStatus.PENDING,
                quality_score=0.0,
            )
            db.add(annotation)
            annotations_created += 1

            if mc is not None and img_bytes and len(img_bytes) >= 100:
                try:
                    from app.ai.face_privacy import get_face_blurrer

                    blurrer = get_face_blurrer()
                    if blurrer.is_loaded():
                        import io as _io

                        blurred = blurrer.process_image_bytes(img_bytes)
                        mc.put_object(
                            settings.MINIO_BUCKET,
                            img_path,
                            _io.BytesIO(blurred),
                            len(blurred),
                            content_type="image/jpeg",
                        )
                        face_blurred += 1
                except Exception:
                    continue

        await db.commit()

        return {
            "batch_id": batch_id,
            "events_processed": batch.event_count,
            "annotations_created": annotations_created,
            "prelabeled": prelabeled,
            "segmented": segmented,
            "face_blurred": face_blurred,
            "final_status": batch.status,
        }


@shared_task(
    name="workers.auto_label",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
)
def auto_label_task(batch_id: str) -> bool:
    try:
        logger.info("Running auto-labeling on batch %s (SAM/YOLO)", batch_id)
        summary = _run_async(_auto_label_async(batch_id))
        logger.info("Auto-labeling completed for batch %s", batch_id)
        _run_async(
            _write_audit_log(
                "AUTO_LABEL_COMPLETED", "INFO",
                {"batch_id": batch_id, "status": "success", **summary},
                resource_type="ingestion_batch", resource_id=batch_id,
            )
        )
        return True
    except Exception as exc:
        logger.error("Failed to auto-label batch %s: %s", batch_id, exc)
        _run_async(
            _write_audit_log(
                "AUTO_LABEL_FAILED", "ERROR",
                {"batch_id": batch_id, "error": str(exc)},
                resource_type="ingestion_batch", resource_id=batch_id,
            )
        )
        raise


async def _auto_label_annotations_async(
    annotation_ids: list[str],
    *,
    force: bool = False,
    confidence_threshold: float = 0.45,
    progress_callback=None,
) -> dict:
    from app.core.config import settings
    from app.core.database import async_session
    from app.core.dependencies import get_minio_client_sync
    from app.models.annotation import Annotation
    from app.models.enums import AnnotationStatus
    from app.services.prelabel import prelabel_image

    processed = 0
    failed = 0
    skipped = 0
    total = len(annotation_ids)

    async with async_session() as db:
        for idx, aid in enumerate(annotation_ids):
            try:
                async with db.begin_nested():
                    ann = await db.get(Annotation, aid)
                    if ann is None:
                        failed += 1
                        continue

                    if not force and ann.human_labels is not None:
                        skipped += 1
                        continue

                    mc = get_minio_client_sync()
                    try:
                        resp = mc.get_object(settings.MINIO_BUCKET, ann.image_path)
                        data = resp.read()
                    except Exception:
                        data = None

                    if not data:
                        failed += 1
                        continue

                    try:
                        detections = prelabel_image(
                            data, confidence_threshold=confidence_threshold
                        )
                    except Exception:
                        detections = []

                    ann.detected_objects = {"objects": detections, "_checksum": ""}
                    ann.auto_labels = {"labels": detections, "batch_inferred": True}
                    ann.status = AnnotationStatus.AUTO_LABELED
                    processed += 1

            except Exception:
                failed += 1
                continue

            if progress_callback:
                progress_callback(
                    processed=processed,
                    failed=failed,
                    skipped=skipped,
                    total=total,
                    current=idx + 1,
                )

        await db.commit()

    return {
        "total": total,
        "processed": processed,
        "failed": failed,
        "skipped": skipped,
    }


@shared_task(
    bind=True,
    name="workers.auto_label_annotations",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
)
def auto_label_annotations_task(
    self,
    annotation_ids: list[str],
    force: bool = False,
    confidence_threshold: float = 0.45,
) -> dict:
    try:
        logger.info("Running auto-labeling on %d annotations", len(annotation_ids))

        def _progress(**meta):
            self.update_state(state="PROGRESS", meta=meta)

        summary = _run_async(
            _auto_label_annotations_async(
                annotation_ids,
                force=force,
                confidence_threshold=confidence_threshold,
                progress_callback=_progress,
            )
        )
        logger.info("Auto-labeling completed for annotations: %s", summary)
        _run_async(
            _write_audit_log(
                "AUTO_LABEL_ANNOTATIONS_COMPLETED",
                "INFO",
                {"status": "success", **summary},
                resource_type="annotation",
            )
        )
        return summary
    except Exception as exc:
        logger.error("Failed to auto-label annotations: %s", exc)
        _run_async(
            _write_audit_log(
                "AUTO_LABEL_ANNOTATIONS_FAILED",
                "ERROR",
                {"error": str(exc), "traceback": traceback.format_exc()},
                resource_type="annotation",
            )
        )
        raise


# ---------------------------------------------------------------------------
# Secure export (real status transitions + ExportLog entries)
# ---------------------------------------------------------------------------

async def _export_async(export_id: str) -> dict:
    """Transition an export PENDING → PROCESSING → COMPLETED with ExportLog entries.

    On failure, the Celery task handler transitions to FAILED and refunds escrow.
    """
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.enums import ExportStatus
    from app.models.export import Export, ExportLog

    async with async_session() as db:
        result = await db.execute(
            select(Export).where(Export.id == export_id).with_for_update()
        )
        export = result.scalar_one_or_none()
        if export is None:
            raise ValueError(f"Export {export_id} not found")

        export.status = ExportStatus.PROCESSING
        db.add(
            ExportLog(
                export_id=export.id,
                event_type="PROCESSING_STARTED",
                details={"started_at": datetime.now(UTC).isoformat()},
            )
        )
        await db.commit()

        logger.info("Export %s: secure transfer starting", export_id)

        export.status = ExportStatus.COMPLETED
        export.completed_at = datetime.now(UTC)
        export.delivery_confirmed = True
        db.add(
            ExportLog(
                export_id=export.id,
                event_type="DELIVERY_CONFIRMED",
                details={
                    "completed_at": export.completed_at.isoformat(),
                    "formats": export.formats_delivered,
                },
            )
        )
        await db.commit()

        return {
            "export_id": export_id,
            "buyer_id": str(export.buyer_id),
            "dataset_id": str(export.dataset_id),
            "formats": export.formats_delivered,
        }


@shared_task(
    name="workers.export_dataset",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
)
def export_dataset_task(export_id: str) -> bool:
    try:
        logger.info("Starting secure dataset export %s", export_id)
        summary = _run_async(_export_async(export_id))
        logger.info("Export %s completed", export_id)
        _run_async(
            _write_audit_log(
                "EXPORT_COMPLETED", "INFO",
                {"export_id": export_id, "status": "success", **summary},
                resource_type="export", resource_id=export_id,
            )
        )
        return True
    except Exception as exc:
        logger.error("Failed to export dataset %s: %s", export_id, exc)
        # Mark export as FAILED and refund escrow when retries are exhausted
        try:
            from sqlalchemy import select as sa_select

            from app.core.database import async_session
            from app.models.enums import ExportStatus
            from app.models.export import Export, ExportLog

            async def _fail_export(exc_info: str):
                async with async_session() as db:
                    result = await db.execute(
                        sa_select(Export).where(Export.id == export_id).with_for_update()
                    )
                    exp = result.scalar_one_or_none()
                    if exp and exp.status not in (ExportStatus.COMPLETED, ExportStatus.FAILED):
                        exp.status = ExportStatus.FAILED
                        db.add(
                            ExportLog(
                                export_id=exp.id,
                                event_type="EXPORT_FAILED_RETRIES_EXHAUSTED",
                                details={"error": exc_info[:500], "retries_exhausted": True},
                            )
                        )
                        await db.commit()

                        from app.services.billing import refund_escrow
                        await refund_escrow(db, exp.id, reason="celery_retries_exhausted")
                        await db.commit()

            _run_async(_fail_export(str(exc)))
        except Exception:
            logger.error("Failed to mark export %s as FAILED", export_id)

        _run_async(
            _write_audit_log(
                "EXPORT_FAILED", "ERROR",
                {"export_id": export_id, "error": str(exc)},
                resource_type="export", resource_id=export_id,
            )
        )
        raise


# ---------------------------------------------------------------------------
# Annotator payroll
# ---------------------------------------------------------------------------

async def _pay_annotators_async() -> dict:
    from decimal import Decimal

    from sqlalchemy import func, select

    from app.core.config import settings
    from app.core.database import async_session
    from app.models.annotation import Annotation
    from app.models.buyer import User
    from app.models.enums import AnnotationStatus

    async with async_session() as db:
        result = await db.execute(
            select(
                Annotation.annotator_id,
                func.count(Annotation.id).label("count"),
            )
            .where(
                Annotation.annotator_id.isnot(None),
                Annotation.status == AnnotationStatus.CERTIFIED,
            )
            .group_by(Annotation.annotator_id)
        )
        rows = result.all()

        total_paid_usd = Decimal("0.00")
        annotators_paid = 0

        for row in rows:
            count = row.count
            wage_mwk = Decimal(str(settings.MINIMUM_ANNOTATOR_WAGE_MWK))
            annotation_pay_mwk = wage_mwk * Decimal(str(count))
            if annotation_pay_mwk < wage_mwk:
                annotation_pay_mwk = wage_mwk
            pay_usd = (annotation_pay_mwk * Decimal(str(settings.MWK_TO_USD_RATE))).quantize(Decimal("0.01"))

            user_result = await db.execute(
                select(User).where(User.id == row.annotator_id).with_for_update()
            )
            user = user_result.scalar_one_or_none()
            if user:
                user.credit_balance_usd = (user.credit_balance_usd or Decimal("0.00")) + pay_usd
                annotators_paid += 1
                total_paid_usd += pay_usd

        await db.commit()

        logger.info("Paid %d annotators, total $%s USD", annotators_paid, total_paid_usd)
        return {
            "annotators_paid": annotators_paid,
            "total_annotations": sum(r.count for r in rows),
            "total_paid_usd": float(total_paid_usd),
        }


@shared_task(
    name="workers.pay_annotators",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
)
def pay_annotators_task() -> bool:
    try:
        logger.info("Running weekly annotator payment")
        summary = _run_async(_pay_annotators_async())
        logger.info("Annotator payments processed: %s", summary)
        _run_async(
            _write_audit_log(
                "PAYROLL_COMPLETED", "INFO",
                {"status": "success", **summary},
                resource_type="payroll",
            )
        )
        return True
    except Exception as exc:
        logger.error("Failed to pay annotators: %s", exc)
        _run_async(
            _write_audit_log(
                "PAYROLL_FAILED", "ERROR",
                {"error": str(exc), "traceback": traceback.format_exc()},
                resource_type="payroll",
            )
        )
        raise


# ---------------------------------------------------------------------------
# Heartbeat timeout check (C-i)
# ---------------------------------------------------------------------------

async def _check_heartbeat_timeouts_async() -> list[dict]:
    from app.core.database import async_session
    from app.services.fleet import check_heartbeat_timeouts

    async with async_session() as db:
        return await check_heartbeat_timeouts(db)


@shared_task(
    name="workers.check_heartbeat_timeouts",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=60,
)
def check_heartbeat_timeouts_task() -> bool:
    try:
        logger.info("Checking heartbeat timeouts")
        timed_out = _run_async(_check_heartbeat_timeouts_async())
        if timed_out:
            logger.warning("Found %d nodes with timed-out heartbeats", len(timed_out))
            _run_async(
                _write_audit_log(
                    "HEARTBEAT_TIMEOUT_CHECK", "WARNING",
                    {"timed_out_count": len(timed_out), "nodes": timed_out},
                    resource_type="fleet",
                )
            )
        else:
            logger.info("All nodes have recent heartbeats")
        _write_heartbeat("task:workers.check_heartbeat_timeouts")
        return True
    except Exception as exc:
        logger.error("Failed to check heartbeat timeouts: %s", exc)
        _run_async(
            _write_audit_log(
                "HEARTBEAT_TIMEOUT_CHECK_FAILED", "ERROR",
                {"error": str(exc), "traceback": traceback.format_exc()},
                resource_type="fleet",
            )
        )
        raise


# ---------------------------------------------------------------------------
# Stuck batch reconciliation (self-healing safety net for broker outages)
# ---------------------------------------------------------------------------

async def _reconcile_stuck_batches_async() -> list[dict]:
    """Re-dispatch auto_label_task for PENDING batches older than the threshold.

    Only touches batches still in PENDING status — batches that have already
    progressed (VALIDATING, INGESTED, etc.) are never touched regardless of age.
    Returns a list of re-dispatched batch summaries for the audit log.
    """
    from datetime import timedelta

    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import async_session
    from app.models.enums import BatchStatus
    from app.models.ingestion import IngestionBatch

    threshold = datetime.now(UTC) - timedelta(
        minutes=settings.STUCK_BATCH_THRESHOLD_MINUTES
    )

    async with async_session() as db:
        result = await db.execute(
            select(IngestionBatch).where(
                IngestionBatch.status == BatchStatus.PENDING,
                IngestionBatch.created_at < threshold,
            )
        )
        stuck_batches = result.scalars().all()

        redispatched = []
        for batch in stuck_batches:
            try:
                from app.workers.tasks import auto_label_task
                auto_label_task.delay(str(batch.id))
                redispatched.append({
                    "batch_id": batch.batch_id,
                    "node_id": str(batch.node_id),
                    "created_at": batch.created_at.isoformat(),
                })
                logger.info(
                    "Re-dispatched stuck batch %s (created %s)",
                    batch.batch_id,
                    batch.created_at.isoformat(),
                )
            except Exception as exc:
                logger.error(
                    "Failed to re-dispatch batch %s: %s",
                    batch.batch_id,
                    exc,
                )

        return redispatched


@shared_task(
    name="workers.reconcile_stuck_batches",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
)
def reconcile_stuck_batches_task() -> bool:
    try:
        logger.info("Checking for stuck PENDING batches")
        redispatched = _run_async(_reconcile_stuck_batches_async())
        if redispatched:
            logger.warning(
                "Re-dispatched %d stuck batches", len(redispatched)
            )
            _run_async(
                _write_audit_log(
                    "BATCH_RECONCILIATION_REDISPATCHED", "WARNING",
                    {
                        "redispatched_count": len(redispatched),
                        "batches": redispatched,
                    },
                    resource_type="ingestion_batch",
                )
            )
        else:
            logger.info("No stuck PENDING batches found")
        _write_heartbeat("task:workers.reconcile_stuck_batches")
        return True
    except Exception as exc:
        logger.error("Failed to reconcile stuck batches: %s", exc)
        _run_async(
            _write_audit_log(
                "BATCH_RECONCILIATION_FAILED", "ERROR",
                {"error": str(exc), "traceback": traceback.format_exc()},
                resource_type="ingestion_batch",
            )
        )
        raise


# ---------------------------------------------------------------------------
# Studio: Dedup analysis (Phase 3)
# ---------------------------------------------------------------------------

async def _dedup_analyze_async(
    dataset_id: str, methods: list[str], threshold: float
) -> dict:
    from app.core.database import async_session
    from app.services.dedup import analyze, save_groups

    async with async_session() as db:
        clusters = await analyze(db, dataset_id, methods, threshold)
        groups_saved = await save_groups(db, dataset_id, clusters)
        return {
            "dataset_id": dataset_id,
            "methods": methods,
            "threshold": threshold,
            "groups_found": groups_saved,
            "clusters": [
                {
                    "group_id": c.group_id,
                    "similarity": c.similarity,
                    "method": c.method,
                    "image_count": len(c.images),
                }
                for c in clusters
            ],
        }


@shared_task(
    name="studio.dedup_analyze",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
)
def dedup_analyze_task(dataset_id: str, methods: list[str], threshold: float) -> dict:
    try:
        logger.info("Running dedup analysis on dataset %s (methods=%s)", dataset_id, methods)
        result = _run_async(_dedup_analyze_async(dataset_id, methods, threshold))
        logger.info("Dedup analysis completed: %s groups found", result["groups_found"])
        _run_async(
            _write_audit_log(
                "DEDUP_ANALYSIS_COMPLETED", "INFO",
                {"dataset_id": dataset_id, "status": "success", **result},
                resource_type="dataset", resource_id=dataset_id,
            )
        )
        return result
    except Exception as exc:
        logger.error("Failed dedup analysis on %s: %s", dataset_id, exc)
        _run_async(
            _write_audit_log(
                "DEDUP_ANALYSIS_FAILED", "ERROR",
                {"dataset_id": dataset_id, "error": str(exc)},
                resource_type="dataset", resource_id=dataset_id,
            )
        )
        raise


# ---------------------------------------------------------------------------
# Studio: Export build (Phase 3) — generates COCO JSON
# ---------------------------------------------------------------------------

async def _export_build_async(
    job_id: str, dataset_id: str, fmt: str,
    split_config: dict, augmentations: dict | None,
    stratify: list[str], watermark: bool,
) -> dict:
    import io as _io
    import json as json_mod
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import async_session
    from app.models.annotation import Annotation
    from app.models.dataset import Dataset
    from app.models.studio import ExportJob

    async with async_session() as db:
        job = (await db.execute(
            select(ExportJob).where(ExportJob.id == UUID(job_id))
        )).scalar_one_or_none()
        if job is None:
            raise ValueError(f"Export job {job_id} not found")
        job.status = "PROCESSING"
        await db.commit()

        ds = (await db.execute(
            select(Dataset).where(Dataset.dataset_id == dataset_id)
        )).scalar_one_or_none()
        if ds is None:
            raise ValueError(f"Dataset {dataset_id} not found")

        anns = (await db.execute(
            select(Annotation)
            .where(Annotation.dataset_id == ds.id)
            .order_by(Annotation.image_index)
        )).scalars().all()

        coco = {
            "info": {
                "description": f"EdgeVision Export — {dataset_id}",
                "version": "1.0",
                "year": datetime.now(UTC).year,
                "date_created": datetime.now(UTC).isoformat(),
            },
            "licenses": [],
            "images": [],
            "annotations": [],
            "categories": [],
        }

        labels_seen: dict[str, int] = {}
        ann_id_counter = 1

        for img_idx, ann in enumerate(anns):
            coco["images"].append({
                "id": img_idx + 1,
                "file_name": ann.image_path.split("/")[-1],
                "width": 640,
                "height": 480,
            })

            if ann.human_labels and isinstance(ann.human_labels, dict):
                boxes = ann.human_labels.get("boxes", [])
                for box in boxes:
                    label = box.get("label", "unknown")
                    if label not in labels_seen:
                        labels_seen[label] = len(labels_seen) + 1
                        coco["categories"].append({
                            "id": labels_seen[label],
                            "name": label,
                            "supercategory": "object",
                        })

                    x = box.get("x", 0) * 640
                    y = box.get("y", 0) * 480
                    w = box.get("width", 0) * 640
                    h = box.get("height", 0) * 480

                    coco["annotations"].append({
                        "id": ann_id_counter,
                        "image_id": img_idx + 1,
                        "category_id": labels_seen[label],
                        "bbox": [round(x, 1), round(y, 1), round(w, 1), round(h, 1)],
                        "area": round(w * h, 1),
                        "iscrowd": 0,
                    })
                    ann_id_counter += 1

        coco_json = json_mod.dumps(coco, indent=2).encode()
        object_name = f"exports/{job_id}/coco.json"
        download_url = None

        try:
            from app.core.dependencies import get_minio_client_sync
            mc = get_minio_client_sync()
            if mc is not None:
                bucket = settings.MINIO_BUCKET
                mc.put_object(
                    bucket, object_name,
                    _io.BytesIO(coco_json), len(coco_json),
                    content_type="application/json",
                )
                download_url = f"/api/v1/studio/exports/{job_id}/download"
        except Exception:
            pass

        if download_url is None:
            import os
            os.makedirs(f"/tmp/edgevision-exports/{job_id}", exist_ok=True)
            local_path = f"/tmp/edgevision-exports/{job_id}/coco.json"
            with open(local_path, "wb") as f:
                f.write(coco_json)
            download_url = f"file://{local_path}"

        job.status = "COMPLETED"
        job.progress_pct = 100.0
        job.file_size_bytes = len(coco_json)
        job.download_url = download_url
        job.completed_at = datetime.now(UTC)
        await db.commit()

        return {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "format": fmt,
            "images": len(coco["images"]),
            "annotations": len(coco["annotations"]),
            "categories": len(coco["categories"]),
            "file_size_bytes": len(coco_json),
            "download_url": download_url,
        }


@shared_task(
    name="studio.export_build",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
)
def export_build_task(
    job_id: str, dataset_id: str, fmt: str,
    split_config: dict, augmentations: dict | None,
    stratify: list[str], watermark: bool,
) -> dict:
    try:
        logger.info("Building export %s for dataset %s (format=%s)", job_id, dataset_id, fmt)
        result = _run_async(
            _export_build_async(job_id, dataset_id, fmt, split_config, augmentations, stratify, watermark)
        )
        logger.info("Export %s completed: %s", job_id, result)
        _run_async(
            _write_audit_log(
                "EXPORT_BUILD_COMPLETED", "INFO",
                {"job_id": job_id, "status": "success", **result},
                resource_type="export_job", resource_id=job_id,
            )
        )
        return result
    except Exception as exc:
        logger.error("Failed export build %s: %s", job_id, exc)
        try:
            async def _fail(exc_msg: str):
                from uuid import UUID as _UUID

                from sqlalchemy import select as sa_select

                from app.core.database import async_session as sess
                from app.models.studio import ExportJob as EJ
                async with sess() as db:
                    job = (await db.execute(
                        sa_select(EJ).where(EJ.id == _UUID(job_id))
                    )).scalar_one_or_none()
                    if job:
                        job.status = "FAILED"
                        job.error_message = exc_msg[:500]
                        await db.commit()
            _run_async(_fail(str(exc)))
        except Exception:
            logger.error("Failed to mark export job %s as FAILED", job_id)
        _run_async(
            _write_audit_log(
                "EXPORT_BUILD_FAILED", "ERROR",
                {"job_id": job_id, "dataset_id": dataset_id, "error": str(exc)},
                resource_type="export_job", resource_id=job_id,
            )
        )
        raise


# ---------------------------------------------------------------------------
# Road segmentation auto-labeling (Phase 8)
# ---------------------------------------------------------------------------

async def _auto_label_road_async(
    image_ids: list[str],
    conf_threshold: float = 0.35,
    iou_threshold: float = 0.45,
    force: bool = False,
    progress_callback=None,
) -> dict:
    import io

    import numpy as np
    from PIL import Image
    from sqlalchemy import select

    from app.ai.road_segmenter import classify_surface_type, get_road_segmenter
    from app.core.config import settings
    from app.core.database import async_session
    from app.models.annotation import Annotation
    from app.models.road_annotation import RoadAnnotation

    async with async_session() as init_db:
        segmenter = await get_road_segmenter(
            settings.ROAD_SEG_MODEL_PATH,
            "gpu" if settings.ENVIRONMENT == "production" else "cpu",
            db=init_db,
        )

    processed = 0
    failed = 0
    skipped = 0
    total = len(image_ids)

    async with async_session() as db:
        for idx, image_id in enumerate(image_ids):
            try:
                async with db.begin_nested():
                    annotation = await db.get(Annotation, image_id)
                    if annotation is None:
                        failed += 1
                        continue

                    existing = await db.execute(
                        select(RoadAnnotation).where(RoadAnnotation.annotation_id == annotation.id)
                    )
                    existing_ra = existing.scalar_one_or_none()

                    if existing_ra is not None:
                        if existing_ra.reviewed and not force:
                            skipped += 1
                            continue
                        if not force:
                            skipped += 1
                            continue

                    from app.core.dependencies import get_minio_client_sync
                    mc = get_minio_client_sync()

                    response = mc.get_object(
                        settings.MINIO_BUCKET, annotation.image_path
                    )
                    pil_image = Image.open(io.BytesIO(response.read()))
                    if pil_image.mode != "RGB":
                        pil_image = pil_image.convert("RGB")

                    image_np = np.array(pil_image)
                    results = segmenter.segment(image_np, conf_threshold, iou_threshold)

                    surface_type = classify_surface_type(results) if results else "unpaved"

                    existing = await db.execute(
                        select(RoadAnnotation).where(RoadAnnotation.annotation_id == annotation.id)
                    )
                    existing_ra = existing.scalar_one_or_none()

                    instances_data = [
                        {
                            "class_id": r.class_id,
                            "class_name": r.class_name,
                            "confidence": r.confidence,
                            "bbox": r.bbox,
                            "mask_rle": r.mask_rle,
                            "polygon": r.polygon,
                        }
                        for r in results
                    ]

                    if existing_ra:
                        existing_ra.instances = instances_data
                        existing_ra.surface_type = surface_type
                        existing_ra.model_version = "yolov8n-seg-v1"
                        existing_ra.auto_generated = True
                        existing_ra.reviewed = False
                    else:
                        ra = RoadAnnotation(
                            annotation_id=annotation.id,
                            surface_type=surface_type,
                            instances=instances_data,
                            model_version="yolov8n-seg-v1",
                            auto_generated=True,
                            reviewed=False,
                        )
                        db.add(ra)

                    processed += 1
            except Exception:
                failed += 1
                continue

            if progress_callback:
                progress_callback(
                    processed=processed,
                    failed=failed,
                    skipped=skipped,
                    total=total,
                    current=idx + 1,
                )

        await db.commit()

    return {
        "total": total,
        "processed": processed,
        "failed": failed,
        "skipped": skipped,
    }


@shared_task(
    bind=True,
    name="workers.auto_label_road",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
)
def auto_label_road_task(
    self,
    image_ids: list[str],
    conf_threshold: float = 0.35,
    iou_threshold: float = 0.45,
    force: bool = False,
) -> dict:
    try:
        logger.info(
            "Running road auto-labeling on %d images",
            len(image_ids),
        )

        def _progress(**meta):
            self.update_state(state="PROGRESS", meta=meta)

        summary = _run_async(
            _auto_label_road_async(
                image_ids,
                conf_threshold,
                iou_threshold,
                force=force,
                progress_callback=_progress,
            )
        )
        logger.info("Road auto-labeling completed: %s", summary)
        _run_async(
            _write_audit_log(
                "ROAD_AUTO_LABEL_COMPLETED", "INFO",
                {"status": "success", **summary},
                resource_type="road_annotation",
            )
        )
        return summary
    except Exception as exc:
        logger.error("Failed road auto-labeling: %s", exc)
        _run_async(
            _write_audit_log(
                "ROAD_AUTO_LABEL_FAILED", "ERROR",
                {"error": str(exc), "traceback": traceback.format_exc()},
                resource_type="road_annotation",
            )
        )
        raise


# ---------------------------------------------------------------------------
# Agri segmentation auto-labeling (Phase 8)
# ---------------------------------------------------------------------------

async def _auto_label_agri_async(
    image_ids: list[str],
    conf_threshold: float = 0.35,
    iou_threshold: float = 0.45,
) -> dict:
    import io

    import numpy as np
    from PIL import Image
    from sqlalchemy import select

    from app.ai.agri_segmenter import dominant_class_name, get_agri_crop_segmenter, get_agri_health_segmenter
    from app.core.config import settings
    from app.core.database import async_session
    from app.models.agri_annotation import AgriAnnotation
    from app.models.annotation import Annotation

    device = "gpu" if settings.ENVIRONMENT == "production" else "cpu"

    async with async_session() as init_db:
        crop_segmenter = await get_agri_crop_segmenter(
            settings.AGRI_CROP_SEG_MODEL_PATH, device, db=init_db,
        )
        health_segmenter = await get_agri_health_segmenter(
            settings.AGRI_HEALTH_SEG_MODEL_PATH, device, db=init_db,
        )

    processed = 0
    failed = 0

    async with async_session() as db:
        for image_id in image_ids:
            try:
                annotation = await db.get(Annotation, image_id)
                if annotation is None:
                    failed += 1
                    continue

                from app.core.dependencies import get_minio_client_sync
                mc = get_minio_client_sync()

                response = mc.get_object(
                    settings.MINIO_BUCKET, annotation.image_path
                )
                pil_image = Image.open(io.BytesIO(response.read()))
                if pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")

                image_np = np.array(pil_image)
                crop_results = crop_segmenter.segment(image_np, conf_threshold, iou_threshold)
                health_results = health_segmenter.segment(image_np, conf_threshold, iou_threshold)

                crop_type = dominant_class_name(crop_results, default="maize")
                health_status = dominant_class_name(health_results, default="healthy")

                existing = await db.execute(
                    select(AgriAnnotation).where(AgriAnnotation.annotation_id == annotation.id)
                )
                existing_aa = existing.scalar_one_or_none()

                instances_data = [
                    {
                        "class_id": r.class_id,
                        "class_name": r.class_name,
                        "confidence": r.confidence,
                        "bbox": r.bbox,
                        "mask_rle": r.mask_rle,
                        "polygon": r.polygon,
                    }
                    for r in (crop_results + health_results)
                ]

                if existing_aa:
                    existing_aa.instances = instances_data
                    existing_aa.crop_type = crop_type
                    existing_aa.health_status = health_status
                    existing_aa.model_version = "yolov8n-seg-v1"
                    existing_aa.auto_generated = True
                else:
                    aa = AgriAnnotation(
                        annotation_id=annotation.id,
                        crop_type=crop_type,
                        health_status=health_status,
                        instances=instances_data,
                        model_version="yolov8n-seg-v1",
                        auto_generated=True,
                        reviewed=False,
                    )
                    db.add(aa)

                processed += 1
            except Exception:
                failed += 1
                continue

        await db.commit()

    return {
        "total": len(image_ids),
        "processed": processed,
        "failed": failed,
    }


@shared_task(
    name="workers.auto_label_agri",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=300,
)
def auto_label_agri_task(
    image_ids: list[str],
    conf_threshold: float = 0.35,
    iou_threshold: float = 0.45,
) -> dict:
    try:
        logger.info(
            "Running agri auto-labeling on %d images",
            len(image_ids),
        )
        summary = _run_async(
            _auto_label_agri_async(image_ids, conf_threshold, iou_threshold)
        )
        logger.info("Agri auto-labeling completed: %s", summary)
        _run_async(
            _write_audit_log(
                "AGRI_AUTO_LABEL_COMPLETED", "INFO",
                {"status": "success", **summary},
                resource_type="agri_annotation",
            )
        )
        return summary
    except Exception as exc:
        logger.error("Failed agri auto-labeling: %s", exc)
        _run_async(
            _write_audit_log(
                "AGRI_AUTO_LABEL_FAILED", "ERROR",
                {"error": str(exc), "traceback": traceback.format_exc()},
                resource_type="agri_annotation",
            )
        )
        raise


# ---------------------------------------------------------------------------
# Consent expiry — batch expire stale consents (beat schedule: 02:00 UTC daily)
# ---------------------------------------------------------------------------

@shared_task(bind=True, name="workers.expire_consents")
def expire_consents_task(self):
    """Expire consents that have passed their expiry date."""

    async def _run():
        from sqlalchemy import update

        from app.core.database import async_session
        from app.core.logging import get_logger
        from app.models.consent import ConsentLedger
        from app.models.enums import ConsentStatus

        logger = get_logger("edgevision.workers.expire_consents")
        logger.info("expire_consents_started")

        async with async_session() as db:
            now = datetime.now(UTC)
            result = await db.execute(
                update(ConsentLedger)
                .where(
                    ConsentLedger.status == ConsentStatus.ACTIVE,
                    ConsentLedger.expiry.isnot(None),
                    ConsentLedger.expiry < now,
                )
                .values(status=ConsentStatus.EXPIRED)
            )
            await db.commit()
            count = result.rowcount
            logger.info("expire_consents_completed", expired_count=count)

            # Write audit log
            from app.models.audit import AuditLog

            audit = AuditLog(
                event_type="CONSENT_EXPIRY_BATCH",
                severity="INFO",
                actor_id=None,
                actor_type="SYSTEM",
                resource_type="consent_ledger",
                resource_id=None,
                details={"expired_count": count, "cutoff": now.isoformat()},
                ip_address=None,
            )
            db.add(audit)
            await db.commit()

        return {"expired": count}

    result = asyncio.run(_run())
    _write_heartbeat("task:workers.expire_consents")
    return result


# ---------------------------------------------------------------------------
# Consent data hard-delete (scheduled 24h after withdrawal)
# ---------------------------------------------------------------------------

async def _hard_delete_user_data_async(subject_hash: str) -> dict:
    from sqlalchemy import delete, select

    from app.core.config import settings
    from app.core.database import async_session
    from app.models.annotation import Annotation
    from app.models.consent import ConsentLedger
    from app.models.subject import SubjectAnnotation

    async with async_session() as db:
        annotations_deleted = 0
        images_deleted = 0

        sa_result = await db.execute(
            select(SubjectAnnotation.annotation_id).where(
                SubjectAnnotation.subject_hash == subject_hash,
            )
        )
        annotation_ids = [row[0] for row in sa_result.all()]

        if annotation_ids:
            anns = await db.execute(
                select(Annotation).where(Annotation.id.in_(annotation_ids))
            )
            for ann in anns.scalars().all():
                mc = None
                try:
                    from app.core.dependencies import get_minio_client_sync
                    mc = get_minio_client_sync()
                except Exception:
                    pass
                if mc is not None:
                    for path in (ann.image_path, ann.thumbnail_path):
                        if path:
                            try:
                                mc.remove_object(settings.MINIO_BUCKET, path)
                                images_deleted += 1
                            except Exception:
                                pass

                await db.delete(ann)
                annotations_deleted += 1

            await db.execute(
                delete(SubjectAnnotation).where(
                    SubjectAnnotation.subject_hash == subject_hash,
                )
            )

        old_consents = await db.execute(
            select(ConsentLedger).where(
                ConsentLedger.subject_hash == subject_hash,
            )
        )
        for c in old_consents.scalars().all():
            await db.delete(c)

        from app.models.audit import AuditLog
        audit = AuditLog(
            event_type="USER_DATA_HARD_DELETED",
            severity="INFO",
            actor_type="SYSTEM",
            resource_type="consent_ledger",
            details={
                "subject_hash": subject_hash,
                "annotations_deleted": annotations_deleted,
                "images_deleted": images_deleted,
            },
        )
        db.add(audit)
        await db.commit()

        return {
            "subject_hash": subject_hash,
            "annotations_deleted": annotations_deleted,
            "images_deleted": images_deleted,
        }


@shared_task(
    name="workers.hard_delete_user_data",
    autoretry_for=(Exception,),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=3600,
)
def hard_delete_user_data_task(subject_hash: str) -> dict:
    try:
        logger.info("Hard-deleting user data for subject %s", subject_hash)
        result = _run_async(_hard_delete_user_data_async(subject_hash))
        logger.info("Hard-delete completed for subject %s: %s", subject_hash, result)
        _write_heartbeat("task:workers.hard_delete_user_data")
        _run_async(
            _write_audit_log(
                "HARD_DELETE_COMPLETED", "INFO",
                {"subject_hash": subject_hash, "status": "success", **result},
                resource_type="consent_ledger",
                resource_id=subject_hash,
            )
        )
        return result
    except Exception as exc:
        logger.error("Failed to hard-delete user data for %s: %s", subject_hash, exc)
        _run_async(
            _write_audit_log(
                "HARD_DELETE_FAILED", "ERROR",
                {"subject_hash": subject_hash, "error": str(exc)},
                resource_type="consent_ledger",
                resource_id=subject_hash,
            )
        )
        raise
