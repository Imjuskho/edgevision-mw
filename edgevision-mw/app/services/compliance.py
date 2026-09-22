from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.annotation import Annotation
from app.models.consent import ConsentLedger
from app.models.dataset import DatasetSubjectMembership
from app.models.enums import AnnotationStatus, ConsentStatus, DatasetStatus, ExportStatus
from app.models.subject import SubjectAnnotation
from app.schemas.compliance import (
    ComplianceAudit,
    ConsentResponse,
    ConsentVerification,
    PIICheckResult,
)

logger = get_logger("edgevision.compliance")


async def record_consent(db: AsyncSession, consent_data: dict) -> ConsentResponse:
    # Create a deterministic anchor hash from consent data
    anchor_data = f"{consent_data['subject_hash']}:{','.join(consent_data['purposes'])}:{datetime.now(UTC).isoformat()}:{secrets.token_hex(16)}"
    tx_hash = hashlib.sha256(anchor_data.encode()).hexdigest()

    # Add timestamp to signed_at if not provided
    if "signed_at" not in consent_data or consent_data["signed_at"] is None:
        consent_data["signed_at"] = datetime.now(UTC)

    # Add expiry if not provided (2 years from now)
    if "expiry" not in consent_data or consent_data["expiry"] is None:
        consent_data["expiry"] = consent_data["signed_at"] + timedelta(days=730)

    consent = ConsentLedger(
        id=uuid4(),
        subject_hash=consent_data["subject_hash"],
        tx_hash=tx_hash,
        purposes=consent_data["purposes"],
        media_types=consent_data["media_types"],
        geography_restrictions=consent_data.get("geography_restrictions", []),
        signed_at=consent_data["signed_at"],
        expiry=consent_data["expiry"],
        guardian_hash=consent_data.get("guardian_hash"),
        signature_bytes=consent_data["signature_bytes"].encode()
        if isinstance(consent_data["signature_bytes"], str)
        else consent_data["signature_bytes"],
        status=ConsentStatus.ACTIVE,
    )
    db.add(consent)
    await db.commit()
    await db.refresh(consent)

    return ConsentResponse(
        id=consent.id,
        subject_hash=consent.subject_hash,
        tx_hash=consent.tx_hash,
        status=consent.status.value,
        signed_at=consent.signed_at,
    )


async def withdraw_consent(db: AsyncSession, subject_hash: str) -> dict:
    now = datetime.now(UTC)

    # 1. Lock active consents with FOR UPDATE to prevent concurrent duplicate withdrawals (M3)
    result = await db.execute(
        select(ConsentLedger)
        .where(
            ConsentLedger.subject_hash == subject_hash,
            ConsentLedger.status == ConsentStatus.ACTIVE,
        )
        .with_for_update()
    )
    active_consents = result.scalars().all()
    affected_count = 0
    for consent in active_consents:
        withdrawal = ConsentLedger(
            id=uuid4(),
            subject_hash=consent.subject_hash,
            tx_hash=f"withdrawal-{uuid4().hex[:16]}",
            purposes=consent.purposes,
            media_types=consent.media_types,
            geography_restrictions=consent.geography_restrictions,
            signed_at=consent.signed_at,
            expiry=consent.expiry,
            guardian_hash=consent.guardian_hash,
            signature_bytes=consent.signature_bytes,
            status=ConsentStatus.WITHDRAWN,
            withdrawn_at=now,
        )
        db.add(withdrawal)
        affected_count += 1

    await db.commit()

    # 2. Find annotations containing this subject via junction table (O(1) lookup)
    from app.models.dataset import Dataset
    from app.models.export import Export

    sa_result = await db.execute(
        select(SubjectAnnotation.annotation_id).where(
            SubjectAnnotation.subject_hash == subject_hash,
        )
    )
    annotation_ids = [row[0] for row in sa_result.all()]

    blocked_annotations = 0
    if annotation_ids:
        ann_result = await db.execute(
            select(Annotation).where(
                Annotation.id.in_(annotation_ids),
                Annotation.status.in_(
                    [
                        AnnotationStatus.CERTIFIED,
                        AnnotationStatus.HUMAN_REVIEW,
                        AnnotationStatus.AUTO_LABELED,
                    ]
                ),
            )
        )
        for ann in ann_result.scalars().all():
            ann.status = AnnotationStatus.REJECTED
            blocked_annotations += 1

    # 3. Block pending exports that contain annotations linked to this subject
    # Chain: subject_hash → subject_annotations.annotation_id → annotations.dataset_id → exports.dataset_id
    blocked_exports = 0
    if annotation_ids:
        ds_result = await db.execute(
            select(func.distinct(Annotation.dataset_id)).where(
                Annotation.id.in_(annotation_ids),
                Annotation.dataset_id.isnot(None),
            )
        )
        dataset_uuids = [row[0] for row in ds_result.all()]

        if dataset_uuids:
            pending_exports_result = await db.execute(
                select(Export).where(
                    Export.dataset_id.in_(dataset_uuids),
                    Export.status.in_([ExportStatus.PENDING, ExportStatus.PROCESSING]),
                )
            )
            for exp in pending_exports_result.scalars().all():
                exp.status = ExportStatus.BLOCKED
                blocked_exports += 1

                # Refund escrowed credit for blocked exports
                from app.services.billing import refund_escrow

                await refund_escrow(db, exp.id, reason="consent_withdrawn")

    # 4. Schedule hard-delete task (24h ETA for data cleanup)
    deletion_failed = False
    try:
        from app.workers.tasks import hard_delete_user_data_task

        hard_delete_user_data_task.apply_async(
            args=[subject_hash],
            countdown=86400,  # 24 hours
        )
    except Exception as e:
        logger.error("Failed to schedule hard-delete for user %s: %s", subject_hash, e)
        deletion_failed = True

    # 6. G1: Query DatasetSubjectMembership for affected datasets and log impact
    ds_membership_result = await db.execute(
        select(DatasetSubjectMembership).where(
            DatasetSubjectMembership.subject_hash == subject_hash,
        )
    )
    affected_memberships = ds_membership_result.scalars().all()

    impact_datasets = []
    for mem in affected_memberships:
        # Look up current dataset status
        ds_result = await db.execute(
            select(Dataset).where(Dataset.dataset_id == mem.dataset_id)
        )
        ds = ds_result.scalar_one_or_none()
        if ds is None:
            continue
        ds_status = ds.status.value if hasattr(ds.status, "value") else ds.status
        if ds_status in (DatasetStatus.FOR_SALE.value, DatasetStatus.SOLD.value):
            impact_datasets.append({
                "dataset_id": mem.dataset_id,
                "dataset_name": ds.name,
                "status": ds_status,
                "subject_annotation_count": mem.annotation_count,
            })

    # 7. Log the withdrawal to audit
    from app.models.audit import AuditLog

    audit_details = {
        "subject_hash": subject_hash,
        "consents_withdrawn": affected_count,
        "annotations_blocked": blocked_annotations,
        "exports_blocked": blocked_exports,
    }
    if impact_datasets:
        audit_details["consent_impact_events"] = impact_datasets

    audit = AuditLog(
        event_type="CONSENT_WITHDRAWN",
        severity="WARNING" if not impact_datasets else "CRITICAL",
        resource_type="consent_ledger",
        details=audit_details,
        actor_type="SYSTEM",
    )
    db.add(audit)

    await db.commit()

    return {
        "subject_hash": subject_hash,
        "consents_withdrawn": affected_count,
        "annotations_blocked": blocked_annotations,
        "exports_blocked": blocked_exports,
        "withdrawn_at": now.isoformat(),
        "deletion_failed": deletion_failed,
        "message": f"Withdrew {affected_count} consents, blocked {blocked_annotations} annotations, blocked {blocked_exports} exports",
    }


async def verify_consent(db: AsyncSession, subject_hash: str, purpose: str) -> ConsentVerification:
    now = datetime.now(UTC)

    # Check if there's a withdrawal record (most recent wins)
    withdrawal_check = await db.execute(
        select(ConsentLedger)
        .where(
            ConsentLedger.subject_hash == subject_hash,
            ConsentLedger.status == ConsentStatus.WITHDRAWN,
        )
        .order_by(ConsentLedger.created_at.desc())
        .limit(1)
    )
    withdrawal = withdrawal_check.scalar_one_or_none()

    # Check for active consent
    result = await db.execute(
        select(ConsentLedger).where(
            ConsentLedger.subject_hash == subject_hash,
            ConsentLedger.status == ConsentStatus.ACTIVE,
        )
    )
    consents = result.scalars().all()

    for consent in consents:
        # If withdrawal happened after this consent, it's invalid
        if withdrawal and consent.created_at < withdrawal.created_at:
            continue
        if purpose in consent.purposes and consent.expiry > now:
            return ConsentVerification(
                valid=True,
                status=consent.status.value if hasattr(consent.status, "value") else consent.status,
                purposes=consent.purposes,
                expiry=consent.expiry,
                affected_images=0,
            )

    return ConsentVerification(
        valid=False,
        status="NOT_FOUND",
        purposes=[],
        expiry=None,
        affected_images=0,
    )


async def run_daily_audit(db: AsyncSession) -> ComplianceAudit:
    now = datetime.now(UTC)

    total_subjects_result = await db.execute(select(func.count(func.distinct(ConsentLedger.subject_hash))))
    total_subjects = total_subjects_result.scalar() or 0

    active_result = await db.execute(
        select(func.count()).select_from(ConsentLedger).where(ConsentLedger.status == ConsentStatus.ACTIVE)
    )
    active_consents = active_result.scalar() or 0

    withdrawn_result = await db.execute(
        select(func.count()).select_from(ConsentLedger).where(ConsentLedger.status == ConsentStatus.WITHDRAWN)
    )
    withdrawn = withdrawn_result.scalar() or 0

    expired_result = await db.execute(
        select(func.count()).select_from(ConsentLedger).where(ConsentLedger.status == ConsentStatus.EXPIRED)
    )
    expired = expired_result.scalar() or 0

    affected_images = withdrawn + expired

    return ComplianceAudit(
        audit_date=now,
        total_subjects=total_subjects,
        active_consents=active_consents,
        withdrawn=withdrawn,
        expired=expired,
        affected_images=affected_images,
        flagged_batches=[],
    )


async def run_pii_check(db: AsyncSession, dataset_id: str) -> PIICheckResult:
    from app.models.annotation import Annotation
    from app.models.dataset import Dataset

    _check_pii_model()

    # Look up the Dataset UUID from the dataset_id string (e.g. "ds-abc123")
    ds_result = await db.execute(select(Dataset).where(Dataset.dataset_id == dataset_id))
    dataset = ds_result.scalar_one_or_none()

    if dataset is None:
        return PIICheckResult(
            dataset_id=dataset_id,
            total_checked=0,
            pii_detected=0,
            detected_types={},
            passed=True,
        )

    result = await db.execute(
        select(Annotation)
        .where(
            Annotation.dataset_id == dataset.id,
        )
        .limit(100)
    )
    annotations = result.scalars().all()

    total_checked = len(annotations)
    pii_detected = 0
    detected_types: dict[str, int] = {}
    violation_details: list[dict] = []

    for ann in annotations:
        labels = ann.auto_labels or ann.human_labels or {}
        if isinstance(labels, dict):
            faces = labels.get("faces", [])
            if faces:
                pii_detected += 1
                detected_types["face"] = detected_types.get("face", 0) + len(faces)
                violation_details.append(
                    {
                        "annotation_id": str(ann.id),
                        "type": "face",
                        "count": len(faces),
                    }
                )

            plates = labels.get("license_plates", [])
            if plates:
                pii_detected += 1
                detected_types["license_plate"] = detected_types.get("license_plate", 0) + len(plates)
                violation_details.append(
                    {
                        "annotation_id": str(ann.id),
                        "type": "license_plate",
                        "count": len(plates),
                    }
                )

    # Vision-based spot check on stored imagery (up to 20 frames).
    vision_scan_failed = False
    vision_failed_count = 0
    vision_total_count = 0
    try:
        from app.ai.pii_redaction import scan_image_bytes
        from app.core.config import settings
        from app.core.dependencies import get_minio_client_sync

        mc = get_minio_client_sync()
        if mc is not None:
            for ann in annotations[:20]:
                if not ann.image_path:
                    continue
                vision_total_count += 1
                try:
                    resp = mc.get_object(settings.MINIO_BUCKET, ann.image_path)
                    scan = scan_image_bytes(resp.read())
                except Exception as e:
                    logger.error("PII vision scan failed for annotation %s: %s", ann.id, e)
                    vision_failed_count += 1
                    vision_scan_failed = True
                    continue
                if scan.faces == -1 or scan.plates == -1:
                    vision_scan_failed = True
                if scan.faces and scan.faces > 0:
                    pii_detected += 1
                    detected_types["face"] = detected_types.get("face", 0) + scan.faces
                    violation_details.append(
                        {
                            "annotation_id": str(ann.id),
                            "type": "face",
                            "count": scan.faces,
                            "source": "vision",
                        }
                    )
                if scan.plates and scan.plates > 0:
                    pii_detected += 1
                    detected_types["license_plate"] = detected_types.get("license_plate", 0) + scan.plates
                    violation_details.append(
                        {
                            "annotation_id": str(ann.id),
                            "type": "license_plate",
                            "count": scan.plates,
                            "source": "vision",
                        }
                    )
            if vision_scan_failed:
                logger.warning(
                    "PII audit completed with %d scan failures out of %d annotations",
                    vision_failed_count,
                    vision_total_count,
                )
    except Exception as e:
        logger.error("PII vision scan failed: %s", e)

    if pii_detected > 0:
        from app.models.audit import AuditLog

        audit = AuditLog(
            event_type="PII_DETECTED",
            severity="WARNING",
            actor_type="SYSTEM",
            resource_type="dataset",
            resource_id=None,
            details={
                "dataset_id": dataset_id,
                "images_checked": total_checked,
                "violations_found": pii_detected,
                "detected_types": detected_types,
            },
        )
        db.add(audit)
        await db.commit()

    return PIICheckResult(
        dataset_id=dataset_id,
        total_checked=total_checked,
        pii_detected=pii_detected,
        detected_types=detected_types,
        passed=pii_detected == 0,
    )


_pii_model_available: bool | None = None


def _check_pii_model() -> bool:
    global _pii_model_available
    if _pii_model_available is not None:
        return _pii_model_available
    try:
        import onnxruntime  # noqa: F401

        _pii_model_available = True
    except ImportError:
        _pii_model_available = False
    return _pii_model_available


async def expire_consents(db: AsyncSession) -> int:
    """Transition ACTIVE consents past their expiry to EXPIRED (H2).

    Append-only: inserts new EXPIRED records rather than updating.
    Returns count of expired consents.
    """
    now = datetime.now(UTC)

    result = await db.execute(
        select(ConsentLedger).where(
            ConsentLedger.status == ConsentStatus.ACTIVE,
            ConsentLedger.expiry <= now,
        )
    )
    expired_consents = result.scalars().all()
    count = 0

    for consent in expired_consents:
        expired_record = ConsentLedger(
            id=uuid4(),
            subject_hash=consent.subject_hash,
            tx_hash=f"expiry-{uuid4().hex[:16]}",
            purposes=consent.purposes,
            media_types=consent.media_types,
            geography_restrictions=consent.geography_restrictions,
            signed_at=consent.signed_at,
            expiry=consent.expiry,
            guardian_hash=consent.guardian_hash,
            signature_bytes=consent.signature_bytes,
            status=ConsentStatus.EXPIRED,
            withdrawn_at=None,
        )
        db.add(expired_record)
        count += 1

    if count > 0:
        from app.models.audit import AuditLog

        audit = AuditLog(
            event_type="CONSENT_EXPIRED",
            severity="INFO",
            resource_type="consent_ledger",
            details={"expired_count": count},
            actor_type="SYSTEM",
        )
        db.add(audit)
        await db.commit()
    else:
        await db.commit()

    return count


async def get_consent_audit(db: AsyncSession) -> dict:
    from datetime import timedelta

    from sqlalchemy import func

    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)

    total_active = await db.execute(
        select(func.count())
        .select_from(ConsentLedger)
        .where(
            ConsentLedger.status == ConsentStatus.ACTIVE,
        )
    )
    total_active_consents = total_active.scalar() or 0

    withdrawn_last_30 = await db.execute(
        select(func.count())
        .select_from(ConsentLedger)
        .where(
            ConsentLedger.status == ConsentStatus.WITHDRAWN,
            ConsentLedger.withdrawn_at >= thirty_days_ago,
        )
    )
    withdrawn_last_30_days = withdrawn_last_30.scalar() or 0

    expired_last_30 = await db.execute(
        select(func.count())
        .select_from(ConsentLedger)
        .where(
            ConsentLedger.status == ConsentStatus.EXPIRED,
            ConsentLedger.created_at >= thirty_days_ago,
        )
    )
    expired_last_30_days = expired_last_30.scalar() or 0

    pending_result = await db.execute(
        select(ConsentLedger)
        .where(
            ConsentLedger.status == ConsentStatus.WITHDRAWN,
            ConsentLedger.hard_deleted_at.is_(None),
        )
        .order_by(ConsentLedger.withdrawn_at.desc())
    )
    pending_consents = pending_result.scalars().all()
    pending_hard_deletions = len(pending_consents)

    pending_deletion_details = []
    for c in pending_consents:
        if c.withdrawn_at:
            pending_deletion_details.append(
                {
                    "subject_hash": c.subject_hash,
                    "withdrawn_at": c.withdrawn_at,
                    "scheduled_hard_delete": c.withdrawn_at + timedelta(hours=24),
                }
            )

    return {
        "total_active_consents": total_active_consents,
        "withdrawn_last_30_days": withdrawn_last_30_days,
        "expired_last_30_days": expired_last_30_days,
        "pending_hard_deletions": pending_hard_deletions,
        "pending_deletion_details": pending_deletion_details,
    }


async def get_subject_withdrawal_impact(
    db: AsyncSession, subject_hash: str
) -> list[dict]:
    """G1: Return all datasets affected by a subject's consent withdrawal."""
    from app.models.dataset import Dataset, DatasetSubjectMembership

    result = await db.execute(
        select(DatasetSubjectMembership).where(
            DatasetSubjectMembership.subject_hash == subject_hash,
        )
    )
    memberships = result.scalars().all()

    affected = []
    for mem in memberships:
        ds_result = await db.execute(
            select(Dataset).where(Dataset.dataset_id == mem.dataset_id)
        )
        ds = ds_result.scalar_one_or_none()
        if ds is None:
            continue
        ds_status = ds.status.value if hasattr(ds.status, "value") else ds.status
        affected.append({
            "dataset_id": mem.dataset_id,
            "dataset_name": ds.name,
            "status": ds_status,
            "subject_annotation_count": mem.annotation_count,
        })

    return affected
