from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.buyer import User
from app.services.billing import send_buyer_notification


@pytest.mark.asyncio
async def test_notification_with_webhook_sends_payload(db_session):
    user = User(
        id=uuid4(),
        email=f"buyer-notify-{uuid4().hex[:8]}@test.com",
        hashed_password="hashed",
        full_name="Test Buyer",
        organization="TestOrg",
        role="BUYER",
        is_active=True,
        dpa_signed=True,
        credit_balance_usd=100.0,
        webhook_url="https://buyer.example.com/hooks/events",
    )
    db_session.add(user)
    await db_session.commit()

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.services.billing.httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        result = await send_buyer_notification(
            db_session,
            user.id,
            "CONSENT_WITHDRAWN",
            {"subject_hash": "abc123"},
        )

    assert result["delivered"] is True
    assert result["attempts"] == 1
    assert result["last_error"] is None

    mock_client_instance.post.assert_called_once()
    call_args = mock_client_instance.post.call_args
    assert call_args[0][0] == "https://buyer.example.com/hooks/events"
    payload = call_args[1]["json"]
    assert payload["event_type"] == "CONSENT_WITHDRAWN"
    assert payload["buyer_id"] == str(user.id)

    audit_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == "BUYER_NOTIFICATION_SENT",
        )
    )
    audits = audit_result.scalars().all()
    matching = [a for a in audits if a.details.get("buyer_id") == str(user.id)]
    assert len(matching) >= 1


@pytest.mark.asyncio
async def test_notification_retries_on_failure(db_session):
    user = User(
        id=uuid4(),
        email=f"buyer-retry-{uuid4().hex[:8]}@test.com",
        hashed_password="hashed",
        full_name="Retry Buyer",
        organization="RetryOrg",
        role="BUYER",
        is_active=True,
        dpa_signed=True,
        credit_balance_usd=50.0,
        webhook_url="https://retry.example.com/hooks",
    )
    db_session.add(user)
    await db_session.commit()

    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.text = "Internal Server Error"

    ok_response = MagicMock()
    ok_response.status_code = 200

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return fail_response
        return ok_response

    with patch("app.services.billing.httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=side_effect)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        with patch("app.services.billing.asyncio.sleep", new_callable=AsyncMock):
            result = await send_buyer_notification(
                db_session,
                user.id,
                "EXPORT_COMPLETED",
                {"export_id": str(uuid4())},
            )

    assert result["delivered"] is True
    assert result["attempts"] == 3


@pytest.mark.asyncio
async def test_notification_no_webhook_skips(db_session):
    user = User(
        id=uuid4(),
        email=f"buyer-noweb-{uuid4().hex[:8]}@test.com",
        hashed_password="hashed",
        full_name="No Webhook Buyer",
        organization="NoWebOrg",
        role="BUYER",
        is_active=True,
        dpa_signed=True,
        credit_balance_usd=25.0,
        webhook_url=None,
    )
    db_session.add(user)
    await db_session.commit()

    result = await send_buyer_notification(
        db_session,
        user.id,
        "CONSENT_WITHDRAWN",
        {"subject_hash": "xyz"},
    )

    assert result["delivered"] is False
    assert result["attempts"] == 0
    assert result["reason"] == "no_webhook_url"

    audit_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == "BUYER_NOTIFICATION_SKIPPED",
        )
    )
    audits = audit_result.scalars().all()
    matching = [a for a in audits if a.details.get("buyer_id") == str(user.id)]
    assert len(matching) >= 1


@pytest.mark.asyncio
async def test_notification_logs_failure_after_max_retries(db_session):
    user = User(
        id=uuid4(),
        email=f"buyer-fail-{uuid4().hex[:8]}@test.com",
        hashed_password="hashed",
        full_name="Fail Buyer",
        organization="FailOrg",
        role="BUYER",
        is_active=True,
        dpa_signed=True,
        credit_balance_usd=10.0,
        webhook_url="https://fail.example.com/hooks",
    )
    db_session.add(user)
    await db_session.commit()

    fail_response = MagicMock()
    fail_response.status_code = 503
    fail_response.text = "Service Unavailable"

    with patch("app.services.billing.httpx.AsyncClient") as MockClient:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=fail_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        with patch("app.services.billing.asyncio.sleep", new_callable=AsyncMock):
            result = await send_buyer_notification(
                db_session,
                user.id,
                "EXPORT_FAILED",
                {"export_id": str(uuid4()), "reason": "timeout"},
            )

    assert result["delivered"] is False
    assert result["attempts"] == 3
    assert "503" in result["last_error"]

    audit_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type == "BUYER_NOTIFICATION_FAILED",
        )
    )
    audits = audit_result.scalars().all()
    matching = [a for a in audits if a.details.get("buyer_id") == str(user.id)]
    assert len(matching) >= 1
    assert matching[0].details["attempts"] == 3
