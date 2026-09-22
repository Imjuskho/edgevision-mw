"""Tests for the Subject Portal API (D3)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import ConsentLedger
from app.models.enums import ConsentStatus
from app.models.subject_reward import SubjectReward


SUBJECT_HASH = "abc123def456"


async def _seed_consent(db: AsyncSession, *, status: ConsentStatus = ConsentStatus.ACTIVE) -> ConsentLedger:
    now = datetime.now(UTC)
    consent = ConsentLedger(
        id=uuid4(),
        subject_hash=SUBJECT_HASH,
        tx_hash=f"tx-{uuid4().hex[:12]}",
        purposes=["road_annotation"],
        media_types=["image"],
        geography_restrictions=[],
        signed_at=now,
        expiry=now + timedelta(days=365),
        signature_bytes=b"\x00" * 64,
        status=status,
    )
    db.add(consent)
    await db.flush()
    return consent


# ── Lookup ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_lookup_creates_portal_token(test_client: AsyncClient, db_session: AsyncSession):
    await _seed_consent(db_session)
    await db_session.commit()

    resp = await test_client.post(
        "/api/v1/subject/lookup",
        json={"subject_hash": SUBJECT_HASH, "phone_number": "+265999123456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["subject_hash"] == SUBJECT_HASH
    assert "portal_token" in data
    assert data["expires_in_hours"] == 168


@pytest.mark.asyncio
async def test_lookup_unknown_subject(test_client: AsyncClient, db_session: AsyncSession):
    await db_session.commit()
    resp = await test_client.post(
        "/api/v1/subject/lookup",
        json={"subject_hash": "unknown_hash", "phone_number": "+265999000000"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_lookup_idempotent_reward_record(test_client: AsyncClient, db_session: AsyncSession):
    await _seed_consent(db_session)
    await db_session.commit()

    # First lookup
    await test_client.post(
        "/api/v1/subject/lookup",
        json={"subject_hash": SUBJECT_HASH, "phone_number": "+265999123456"},
    )
    # Second lookup should not create duplicate reward
    resp = await test_client.post(
        "/api/v1/subject/lookup",
        json={"subject_hash": SUBJECT_HASH, "phone_number": "+265999123456"},
    )
    assert resp.status_code == 200

    # Verify only one reward record exists
    from sqlalchemy import select, func
    from app.models.subject_reward import SubjectReward as SR

    count_result = await db_session.execute(select(func.count()).select_from(SR).where(SR.subject_hash == SUBJECT_HASH))
    assert count_result.scalar() == 1


# ── History ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_history_returns_empty(test_client: AsyncClient, db_session: AsyncSession):
    await _seed_consent(db_session)
    await db_session.commit()

    resp = await test_client.get(f"/api/v1/subject/{SUBJECT_HASH}/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["subject_hash"] == SUBJECT_HASH
    assert data["capture_count"] == 0
    assert data["consent_status"]["status"] == "ACTIVE"
    assert float(data["reward_balance_mwk"]) == 0.00


@pytest.mark.asyncio
async def test_history_with_reward_balance(test_client: AsyncClient, db_session: AsyncSession):
    await _seed_consent(db_session)
    reward = SubjectReward(
        id=uuid4(),
        subject_hash=SUBJECT_HASH,
        phone_number="+265999123456",
        total_airtime_mwk=Decimal("2500.00"),
        pending_airtime_mwk=Decimal("1500.00"),
        is_active=True,
    )
    db_session.add(reward)
    await db_session.commit()

    resp = await test_client.get(f"/api/v1/subject/{SUBJECT_HASH}/history")
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["reward_balance_mwk"]) == 1500.00
    assert float(data["total_earned_mwk"]) == 2500.00


@pytest.mark.asyncio
async def test_history_unknown_subject(test_client: AsyncClient, db_session: AsyncSession):
    await db_session.commit()
    resp = await test_client.get("/api/v1/subject/nonexistent_hash/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capture_count"] == 0


# ── Withdraw ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_withdraw_opt_out(test_client: AsyncClient, db_session: AsyncSession):
    await _seed_consent(db_session)
    await db_session.commit()

    resp = await test_client.post(
        f"/api/v1/subject/{SUBJECT_HASH}/withdraw",
        json={"subject_hash": SUBJECT_HASH, "reason": "No longer want to participate"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "withdrawn"


@pytest.mark.asyncio
async def test_withdraw_with_reward(test_client: AsyncClient, db_session: AsyncSession):
    await _seed_consent(db_session)
    reward = SubjectReward(
        id=uuid4(),
        subject_hash=SUBJECT_HASH,
        total_airtime_mwk=Decimal("1000.00"),
        pending_airtime_mwk=Decimal("500.00"),
        is_active=True,
    )
    db_session.add(reward)
    await db_session.commit()

    resp = await test_client.post(
        f"/api/v1/subject/{SUBJECT_HASH}/withdraw",
        json={"subject_hash": SUBJECT_HASH},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "withdrawn"


# ── Rewards ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_rewards(test_client: AsyncClient, db_session: AsyncSession):
    reward = SubjectReward(
        id=uuid4(),
        subject_hash=SUBJECT_HASH,
        total_airtime_mwk=Decimal("3000.00"),
        pending_airtime_mwk=Decimal("1000.00"),
        is_active=True,
    )
    db_session.add(reward)
    await db_session.commit()

    resp = await test_client.get(f"/api/v1/subject/{SUBJECT_HASH}/rewards")
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["total_airtime_mwk"]) == 3000.00
    assert float(data["pending_airtime_mwk"]) == 1000.00
    assert data["payout_method"] == "airtime"


@pytest.mark.asyncio
async def test_get_rewards_no_record(test_client: AsyncClient, db_session: AsyncSession):
    await db_session.commit()
    resp = await test_client.get("/api/v1/subject/unknown_hash/rewards")
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["total_airtime_mwk"]) == 0.00
    assert float(data["pending_airtime_mwk"]) == 0.00
