from __future__ import annotations

import copy

import pytest
from sqlalchemy import select

from app.models.annotation import Annotation
from app.models.enums import AnnotationStatus
from app.models.studio import AnnotationAction
from tests.test_studio import (
    _create_annotation,
    _create_batch,
    _create_dataset,
    _create_user,
    _make_token,
)
from tests.conftest import _create_node


async def _create_session(test_client, token, ds):
    resp = await test_client.post(
        "/api/v1/studio/sessions",
        json={"dataset_id": str(ds.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_review_submit_decision_approved_certifies(db_session, test_client):
    """Regression: decision=approved → processed:1, CERTIFIED, review_approved action."""
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    ann = await _create_annotation(
        db_session,
        ds.id,
        batch.id,
        index=0,
    )
    token = _make_token(user)
    session_id = await _create_session(test_client, token, ds)

    resp = await test_client.post(
        f"/api/v1/studio/sessions/{session_id}/review-submit",
        json={
            "actions": [
                {"image_id": str(ann.id), "decision": "approved"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["processed"] == 1
    assert body["results"][0]["decision"] == "approved"

    await db_session.refresh(ann)
    assert ann.status == AnnotationStatus.CERTIFIED
    assert ann.is_certified is True

    actions = (
        (
            await db_session.execute(
                select(AnnotationAction).where(
                    AnnotationAction.session_id == session_id,
                    AnnotationAction.annotation_id == ann.id,
                )
            )
        )
        .scalars()
        .all()
    )
    action_types = {a.action_type for a in actions}
    assert "review_approved" in action_types


@pytest.mark.asyncio
async def test_review_submit_legacy_action_alias(db_session, test_client):
    """Legacy action=approve maps to approved."""
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    ann = await _create_annotation(db_session, ds.id, batch.id, index=0)
    token = _make_token(user)
    session_id = await _create_session(test_client, token, ds)

    resp = await test_client.post(
        f"/api/v1/studio/sessions/{session_id}/review-submit",
        json={"actions": [{"image_id": str(ann.id), "action": "approve"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["processed"] == 1

    await db_session.refresh(ann)
    assert ann.status == AnnotationStatus.CERTIFIED


@pytest.mark.asyncio
async def test_review_submit_flagged_stays_pending(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    ann = await _create_annotation(db_session, ds.id, batch.id, index=0)
    token = _make_token(user)
    session_id = await _create_session(test_client, token, ds)

    resp = await test_client.post(
        f"/api/v1/studio/sessions/{session_id}/review-submit",
        json={"actions": [{"image_id": str(ann.id), "decision": "flagged"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["processed"] == 1

    await db_session.refresh(ann)
    assert ann.status == AnnotationStatus.PENDING
    assert ann.is_certified is False

    action = (
        await db_session.execute(
            select(AnnotationAction).where(
                AnnotationAction.annotation_id == ann.id,
                AnnotationAction.action_type == "review_flagged",
            )
        )
    ).scalar_one()
    assert action.payload["decision"] == "flagged"


@pytest.mark.asyncio
async def test_review_submit_persists_refines(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    human = {"boxes": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4, "label": "car"}]}
    ann = Annotation(
        batch_id=batch.id,
        image_index=0,
        image_path="images/refine.jpg",
        thumbnail_path="thumbs/refine.jpg",
        detected_objects={
            "objects": [
                {
                    "class_name": "car",
                    "confidence": 0.9,
                    "track_id": 1,
                    "mask": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5]],
                    "bbox_3d": {
                        "corners": [
                            [0.1, 0.1, 0],
                            [0.2, 0.1, 0],
                            [0.2, 0.2, 0],
                            [0.1, 0.2, 0],
                            [0.1, 0.1, 1],
                            [0.2, 0.1, 1],
                            [0.2, 0.2, 1],
                            [0.1, 0.2, 1],
                        ]
                    },
                }
            ]
        },
        auto_labels={"labels": []},
        human_labels=copy.deepcopy(human),
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
        dataset_id=ds.id,
    )
    db_session.add(ann)
    await db_session.commit()
    await db_session.refresh(ann)

    token = _make_token(user)
    session_id = await _create_session(test_client, token, ds)

    refines = [
        {
            "object_index": 0,
            "mask": [[0.15, 0.15], [0.55, 0.15], [0.55, 0.55]],
            "bbox_3d": {
                "corners": [
                    [0.15, 0.15, 0],
                    [0.25, 0.15, 0],
                    [0.25, 0.25, 0],
                    [0.15, 0.25, 0],
                    [0.15, 0.15, 1],
                    [0.25, 0.15, 1],
                    [0.25, 0.25, 1],
                    [0.15, 0.25, 1],
                ],
            },
        }
    ]

    resp = await test_client.post(
        f"/api/v1/studio/sessions/{session_id}/review-submit",
        json={
            "actions": [
                {"image_id": str(ann.id), "decision": "approved", "refines": refines},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    await db_session.refresh(ann)
    assert ann.qa_labels is not None
    assert ann.qa_labels["refines"] == refines
    assert ann.human_labels == human

    refine_action = (
        await db_session.execute(
            select(AnnotationAction).where(
                AnnotationAction.annotation_id == ann.id,
                AnnotationAction.action_type == "refine",
            )
        )
    ).scalar_one()
    assert refine_action.payload["refines"] == refines


@pytest.mark.asyncio
async def test_review_submit_refine_validation_rejects_bad_coords(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    ann = await _create_annotation(db_session, ds.id, batch.id, index=0)
    token = _make_token(user)
    session_id = await _create_session(test_client, token, ds)

    resp = await test_client.post(
        f"/api/v1/studio/sessions/{session_id}/review-submit",
        json={
            "actions": [
                {
                    "image_id": str(ann.id),
                    "decision": "approved",
                    "refines": [{"object_index": 0, "mask": [[1.5, 0.5]]}],
                },
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_review_submit_refine_validation_rejects_too_many_points(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    ann = await _create_annotation(db_session, ds.id, batch.id, index=0)
    token = _make_token(user)
    session_id = await _create_session(test_client, token, ds)

    mask = [[0.01 * i, 0.01 * i] for i in range(33)]
    resp = await test_client.post(
        f"/api/v1/studio/sessions/{session_id}/review-submit",
        json={
            "actions": [
                {"image_id": str(ann.id), "decision": "approved", "refines": [{"object_index": 0, "mask": mask}]},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_review_submit_refine_validation_requires_eight_corners(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    ann = await _create_annotation(db_session, ds.id, batch.id, index=0)
    token = _make_token(user)
    session_id = await _create_session(test_client, token, ds)

    resp = await test_client.post(
        f"/api/v1/studio/sessions/{session_id}/review-submit",
        json={
            "actions": [
                {
                    "image_id": str(ann.id),
                    "decision": "approved",
                    "refines": [{"object_index": 0, "bbox_3d": {"corners": [[0, 0, 0], [1, 1, 0]]}}],
                },
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_review_queue_passthrough_detected_objects(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    ann = Annotation(
        batch_id=batch.id,
        image_index=0,
        image_path="images/queue.jpg",
        thumbnail_path="thumbs/queue.jpg",
        detected_objects={
            "objects": [
                {
                    "class_name": "person",
                    "confidence": 0.88,
                    "track_id": 7,
                    "mask": [[0, 0], [0.5, 0], [0.5, 0.5]],
                    "bbox_3d": {"corners": [[0, 0, 0]] * 8},
                }
            ]
        },
        auto_labels={"labels": []},
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
        dataset_id=ds.id,
    )
    db_session.add(ann)
    await db_session.commit()

    token = _make_token(user)
    session_id = await _create_session(test_client, token, ds)

    resp = await test_client.get(
        f"/api/v1/studio/sessions/{session_id}/review-queue?limit=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    images = resp.json()["images"]
    assert len(images) >= 1
    target = next(i for i in images if i["id"] == str(ann.id))
    assert "detected_objects" in target
    assert target["detected_objects"][0]["confidence"] == 0.88
    assert target["detected_objects"][0]["track_id"] == 7
    assert target["detected_objects"][0]["mask"] == [[0, 0], [0.5, 0], [0.5, 0.5]]
    assert "has_human_labels" in target
    assert "annotations" in target
    assert "image_index" in target
    assert target["image_index"] == ann.image_index


@pytest.mark.asyncio
async def test_get_annotation_exposes_qa_refines(db_session, test_client):
    user = await _create_user(db_session)
    node = await _create_node(db_session)
    batch = await _create_batch(db_session, node)
    ds = await _create_dataset(db_session)
    refines = [{"object_index": 0, "mask": [[0.2, 0.2], [0.8, 0.2], [0.5, 0.8]]}]
    ann = Annotation(
        batch_id=batch.id,
        image_index=0,
        image_path="images/qa.jpg",
        thumbnail_path="thumbs/qa.jpg",
        detected_objects={"objects": []},
        auto_labels={"labels": []},
        qa_labels={"refines": refines},
        status=AnnotationStatus.PENDING,
        quality_score=0.0,
        dataset_id=ds.id,
    )
    db_session.add(ann)
    await db_session.commit()
    await db_session.refresh(ann)

    token = _make_token(user)
    resp = await test_client.get(
        f"/api/v1/studio/annotations/{ann.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["qa_labels"]["refines"] == refines
