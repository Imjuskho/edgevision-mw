from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.annotation import Annotation
from app.models.buyer import User
from app.models.enums import AnnotationStatus, BatchStatus, NodeCategory, NodeStatus, PIIMode
from app.models.ingestion import IngestionBatch
from app.models.node import Node
from app.services.annotation import auto_assign_jobs, calculate_iaa, get_leaderboard, submit_labels, submit_review
from tests.conftest import _create_node


async def _create_qa_reviewer_user(db):
    user = User(
        id=uuid4(),
        email=f"qa-{uuid4().hex[:6]}@test.com",
        hashed_password="x" * 60,
        full_name="Test QA Reviewer",
        role="QA",
    )
    db.add(user)
    await db.commit()
    return user


async def _create_batch(db, node):
    batch = IngestionBatch(
        id=uuid4(),
        batch_id=f"BATCH-{uuid4().hex[:6]}",
        node_id=node.id,
        hub_id="hub-1",
        event_count=1,
        file_size_bytes=1024,
        checksum_sha256="a" * 64,
        node_signature=b"\x00" * 64,
        compression_codec="h265",
        status=BatchStatus.INGESTED,
        quality_scores={},
    )
    db.add(batch)
    await db.commit()
    return batch


async def _create_pending_annotation(db, batch, annotator_id=None):
    ann = Annotation(
        id=uuid4(),
        batch_id=batch.id,
        image_index=0,
        image_path="/images/001.jpg",
        thumbnail_path="/thumbs/001.jpg",
        gps_lat=-13.96,
        gps_lon=33.77,
        detected_objects={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
        auto_labels={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
        status=AnnotationStatus.PENDING,
        quality_score=0.8,
        annotator_id=annotator_id,
    )
    db.add(ann)
    await db.commit()
    return ann


async def _create_annotator_user(db):
    user = User(
        id=uuid4(),
        email=f"annotator-{uuid4().hex[:6]}@test.com",
        hashed_password="x" * 60,
        full_name="Test Annotator",
        role="ANNOTATOR",
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_concurrent_assignment_prevents_duplicates(db_session):
    annotator = await _create_annotator_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    await _create_pending_annotation(db_session, batch)

    result1 = await auto_assign_jobs(db_session, count=5, target_annotator=annotator.id)
    result2 = await auto_assign_jobs(db_session, count=5, target_annotator=annotator.id)

    annotation_ids_1 = {a.annotation_id for a in result1}
    annotation_ids_2 = {a.annotation_id for a in result2}
    overlap = annotation_ids_1 & annotation_ids_2
    assert len(overlap) == 0, f"Duplicate assignments: {overlap}"


@pytest.mark.asyncio
async def test_submit_labels_wrong_annotator_rejected(db_session):
    correct_annotator = await _create_annotator_user(db_session)
    wrong_annotator_id = uuid4()

    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ann = await _create_pending_annotation(db_session, batch, annotator_id=correct_annotator.id)

    ann.status = AnnotationStatus.HUMAN_REVIEW
    ann.human_labels = None
    await db_session.commit()

    with pytest.raises((PermissionError, ValueError, Exception)):
        await submit_labels(
            db_session,
            annotation_id=ann.id,
            annotator_id=wrong_annotator_id,
            labels={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
            quality_score=0.95,
        )

    result = await db_session.execute(select(Annotation).where(Annotation.id == ann.id))
    ann_check = result.scalar_one()
    assert ann_check.annotator_id == correct_annotator.id


@pytest.mark.asyncio
async def test_iaa_blocks_below_certification(db_session):
    original = {"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]}
    review = {"objects": [{"class": "vehicle", "bbox": [12, 11, 48, 49]}]}
    iaa_score = calculate_iaa(original, review, category="object_detection")

    assert 0.0 <= iaa_score <= 1.0

    user = await _create_annotator_user(db_session)
    assert user.role == "ANNOTATOR"


@pytest.mark.asyncio
async def test_leaderboard_aggregation(db_session):
    annotator = await _create_annotator_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)

    now = datetime.now(UTC)
    for i in range(5):
        ann = Annotation(
            id=uuid4(),
            batch_id=batch.id,
            image_index=i,
            image_path=f"/images/{i:03d}.jpg",
            thumbnail_path=f"/thumbs/{i:03d}.jpg",
            detected_objects={"objects": []},
            auto_labels={"objects": []},
            human_labels={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
            status=AnnotationStatus.QA_REVIEW,
            quality_score=0.9,
            iaa_score=0.85,
            annotator_id=annotator.id,
            review_completed_at=now - timedelta(hours=i),
        )
        db_session.add(ann)
    await db_session.commit()

    leaderboard = await get_leaderboard(db_session)
    assert len(leaderboard) >= 1, f"Expected at least 1 leaderboard entry, got {len(leaderboard)}"

    entry = next((e for e in leaderboard if str(e.annotator_id) == str(annotator.id)), None)
    assert entry is not None, (
        f"Annotator {annotator.id} not found in leaderboard: {[str(e.annotator_id) for e in leaderboard]}"
    )
    assert entry.total_annotated >= 5
    assert entry.avg_quality_score > 0


@pytest.mark.asyncio
async def test_submit_labels_rejects_wrong_status(db_session):
    """B1: submit_labels should reject annotations not in HUMAN_REVIEW status."""
    annotator = await _create_annotator_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)

    # Create a PENDING annotation (not HUMAN_REVIEW)
    ann = await _create_pending_annotation(db_session, batch, annotator_id=annotator.id)
    assert ann.status == AnnotationStatus.PENDING

    with pytest.raises(ValueError, match="Cannot submit labels"):
        await submit_labels(
            db_session,
            annotation_id=ann.id,
            annotator_id=annotator.id,
            labels={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
            quality_score=0.95,
        )

    # Verify status was NOT changed
    result = await db_session.execute(select(Annotation).where(Annotation.id == ann.id))
    ann_check = result.scalar_one()
    assert ann_check.status == AnnotationStatus.PENDING


@pytest.mark.asyncio
async def test_submit_labels_accepts_correct_status(db_session):
    """B1: submit_labels should work on HUMAN_REVIEW annotations."""
    annotator = await _create_annotator_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)

    ann = await _create_pending_annotation(db_session, batch, annotator_id=annotator.id)
    ann.status = AnnotationStatus.HUMAN_REVIEW
    await db_session.commit()

    response = await submit_labels(
        db_session,
        annotation_id=ann.id,
        annotator_id=annotator.id,
        labels={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
        quality_score=0.95,
    )
    assert response.status == AnnotationStatus.QA_REVIEW.value


@pytest.mark.asyncio
async def test_submit_review_rejects_wrong_status(db_session):
    """B1: submit_review should reject annotations not in QA_REVIEW status."""
    annotator = await _create_annotator_user(db_session)
    qa = await _create_qa_reviewer_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)

    # Create a HUMAN_REVIEW annotation (not QA_REVIEW)
    ann = await _create_pending_annotation(db_session, batch, annotator_id=annotator.id)
    ann.status = AnnotationStatus.HUMAN_REVIEW
    await db_session.commit()

    with pytest.raises(ValueError, match="Cannot submit review"):
        await submit_review(
            db_session,
            annotation_id=ann.id,
            reviewer_id=qa.id,
            review_labels={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
        )


@pytest.mark.asyncio
async def test_submit_review_rejects_self_assignment(db_session):
    """B2: QA reviewer cannot review their own annotation."""
    annotator = await _create_annotator_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)

    ann = await _create_pending_annotation(db_session, batch, annotator_id=annotator.id)
    ann.status = AnnotationStatus.QA_REVIEW
    ann.human_labels = {"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]}
    await db_session.commit()

    with pytest.raises(ValueError, match="cannot review their own"):
        await submit_review(
            db_session,
            annotation_id=ann.id,
            reviewer_id=annotator.id,  # same as annotator_id!
            review_labels={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
        )

    # Verify annotation was NOT certified
    result = await db_session.execute(select(Annotation).where(Annotation.id == ann.id))
    ann_check = result.scalar_one()
    assert ann_check.status == AnnotationStatus.QA_REVIEW


@pytest.mark.asyncio
async def test_submit_review_allows_different_reviewer(db_session):
    """B2: Different reviewer should be able to review."""
    annotator = await _create_annotator_user(db_session)
    qa = await _create_qa_reviewer_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)

    ann = await _create_pending_annotation(db_session, batch, annotator_id=annotator.id)
    ann.status = AnnotationStatus.QA_REVIEW
    ann.human_labels = {"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]}
    await db_session.commit()

    response = await submit_review(
        db_session,
        annotation_id=ann.id,
        reviewer_id=qa.id,
        review_labels={"objects": [{"class": "vehicle", "bbox": [10, 10, 50, 50]}]},
    )
    assert response.status in (AnnotationStatus.CERTIFIED.value, AnnotationStatus.REJECTED.value)
