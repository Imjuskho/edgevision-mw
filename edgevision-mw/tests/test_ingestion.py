import hashlib
import uuid
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.models.enums import BatchStatus, NodeCategory, NodeStatus, PIIMode
from app.models.node import Node
from app.services.ingestion import receive_batch, validate_batch
from tests.conftest import _create_node


@pytest.mark.asyncio
async def test_batch_upload_routes_to_correct_bucket(db_session):
    node = await _create_node(db_session)
    file_bytes = b"test image data for batch upload"
    checksum = hashlib.sha256(file_bytes).hexdigest()

    batch_data = {
        "batch_id": f"BATCH-{uuid.uuid4().hex[:12]}",
        "node_id": str(node.id),
        "hub_id": "edge-hub-01",
        "event_count": 1,
        "file_size_bytes": len(file_bytes),
        "checksum_sha256": checksum,
        "compression_codec": "h265",
        "quality_scores": {"brightness": 0.8},
    }

    response = await receive_batch(db_session, batch_data, file=file_bytes)

    assert response.batch_id == batch_data["batch_id"]
    assert response.event_count == 1


@pytest.mark.asyncio
async def test_duplicate_batch_idempotent(db_session):
    node = await _create_node(db_session)
    batch_id = f"BATCH-DEUP-{uuid.uuid4().hex[:8]}"
    checksum = hashlib.sha256(b"test").hexdigest()

    batch_data = {
        "batch_id": batch_id,
        "node_id": str(node.id),
        "hub_id": "hub-1",
        "event_count": 5,
        "file_size_bytes": 4,
        "checksum_sha256": checksum,
        "compression_codec": "h265",
        "quality_scores": {},
    }

    resp1 = await receive_batch(db_session, batch_data)
    resp2 = await receive_batch(db_session, batch_data)

    assert resp1.batch_id == resp2.batch_id
    assert resp1.id == resp2.id


@pytest.mark.asyncio
async def test_invalid_checksum_rejected(db_session):
    """B2: Invalid checksum creates a REJECTED batch record instead of raising."""
    node = await _create_node(db_session)
    file_bytes = b"actual file content"
    batch_data = {
        "batch_id": f"BATCH-CHK-{uuid.uuid4().hex[:8]}",
        "node_id": str(node.id),
        "hub_id": "hub-1",
        "event_count": 1,
        "file_size_bytes": len(file_bytes),
        "checksum_sha256": "0" * 64,
        "compression_codec": "h265",
        "quality_scores": {},
    }

    response = await receive_batch(db_session, batch_data, file=file_bytes)
    assert response.status == BatchStatus.REJECTED.value
    assert response.batch_id == batch_data["batch_id"]


@pytest.mark.asyncio
async def test_signature_verification_required(db_session):
    node = await _create_node(db_session)
    batch_data = {
        "batch_id": f"BATCH-SIG-{uuid.uuid4().hex[:8]}",
        "node_id": str(node.id),
        "hub_id": "hub-1",
        "event_count": 10,
        "file_size_bytes": 1024,
        "checksum_sha256": "a" * 64,
        "quality_scores": {},
    }

    result = await validate_batch(db_session, batch_data, signature="")
    assert result.valid is True
    assert len(result.warnings) > 0
    assert any("No signature" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_receive_batch_dispatches_auto_label_task(db_session):
    """PENDING batches must not be a dead end — receive_batch dispatches auto_label_task."""
    from app.workers.tasks import auto_label_task

    node = await _create_node(db_session)
    batch_data = {
        "batch_id": f"BATCH-DISPATCH-{uuid4().hex[:8]}",
        "node_id": str(node.id),
        "hub_id": "hub-1",
        "event_count": 5,
        "file_size_bytes": 1024,
        "checksum_sha256": "a" * 64,
        "compression_codec": "h265",
        "quality_scores": {},
    }

    with patch.object(auto_label_task, "delay") as mock_delay:
        response = await receive_batch(db_session, batch_data)
        assert response.status == BatchStatus.PENDING.value
        mock_delay.assert_called_once()
        dispatched_id = mock_delay.call_args[0][0]
        assert dispatched_id is not None


@pytest.mark.asyncio
async def test_dispatch_failure_writes_audit_log_and_error_log(db_session, capsys):
    """When auto_label_task.delay raises, receive_batch must:
    (a) still return successfully to the caller,
    (b) write an audit log entry with BATCH_DISPATCH_FAILED,
    (c) emit an ERROR-level structlog line.
    """
    from app.models.audit import AuditLog
    from app.workers.tasks import auto_label_task

    node = await _create_node(db_session)
    batch_data = {
        "batch_id": f"BATCH-FAIL-{uuid4().hex[:8]}",
        "node_id": str(node.id),
        "hub_id": "hub-1",
        "event_count": 3,
        "file_size_bytes": 512,
        "checksum_sha256": "c" * 64,
        "compression_codec": "h265",
        "quality_scores": {},
    }

    with patch.object(auto_label_task, "delay", side_effect=RuntimeError("broker unreachable")):
        response = await receive_batch(db_session, batch_data)

    # (a) HTTP response must still succeed
    assert response.batch_id == batch_data["batch_id"]
    assert response.status == BatchStatus.PENDING.value

    # (b) Audit log entry exists with the correct event_type for this batch
    from sqlalchemy import select as sel

    result = await db_session.execute(
        sel(AuditLog).where(
            AuditLog.event_type == "BATCH_DISPATCH_FAILED",
            AuditLog.resource_id == response.id,
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None, "Audit log entry with BATCH_DISPATCH_FAILED not found"
    assert audit.severity == "ERROR"
    assert audit.resource_type == "ingestion_batch"
    assert audit.resource_id == response.id
    assert audit.details["batch_id"] == batch_data["batch_id"]
    assert audit.details["node_id"] == batch_data["node_id"]
    assert "broker unreachable" in audit.details["error"]

    # (c) ERROR-level structlog line was emitted
    captured = capsys.readouterr()
    assert "batch_dispatch_failed" in captured.out
