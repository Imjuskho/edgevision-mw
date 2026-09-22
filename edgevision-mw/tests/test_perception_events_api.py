from __future__ import annotations

import pytest
from datetime import UTC, datetime
from sqlalchemy import select

from app.models.perception_event import PerceptionEvent
from app.models.workspace_settings import WorkspaceSettings


def _create_token(user):
    from app.core.security import create_access_token

    return create_access_token(data={"sub": str(user.id), "role": user.role})


@pytest.mark.asyncio
async def test_event_rules_defaults_when_unset(test_client, db_session):
    from tests.test_phase7 import _create_user

    admin = await _create_user(db_session, role="ADMIN")
    token = _create_token(admin)

    resp = await test_client.get(
        "/api/v1/annotations/event-rules",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["rules"], list)
    assert len(data["rules"]) >= 3
    rule_ids = {r["rule_id"] for r in data["rules"]}
    assert "dwell_pedestrian_roadside" in rule_ids
    assert "dwell_vehicle" in rule_ids


@pytest.mark.asyncio
async def test_update_event_rules_persists(test_client, db_session):
    from tests.test_phase7 import _create_user

    admin = await _create_user(db_session, role="ADMIN")
    token = _create_token(admin)

    payload = {
        "rules": [
            {
                "rule_id": "dwell_pedestrian_roadside",
                "name": "Pedestrian dwell",
                "rule_type": "dwell",
                "class_name": "person",
                "taxonomy_labels": ["pedestrian_roadside"],
                "dwell_seconds": 12.0,
                "distance_threshold": None,
                "time_of_day": None,
                "cooldown_seconds": 30.0,
                "auto_save": True,
                "enabled": True,
            }
        ]
    }

    resp = await test_client.put(
        "/api/v1/annotations/event-rules",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["rules"][0]["dwell_seconds"] == 12.0

    setting = await db_session.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.singleton_key == "default")
    )
    record = setting.scalar_one()
    stored = record.operational_json.get("perception_event_rules", [])
    assert stored[0]["dwell_seconds"] == 12.0


@pytest.mark.asyncio
async def test_update_event_rules_requires_admin(test_client, db_session):
    from tests.test_phase7 import _create_user

    operator = await _create_user(db_session, role="OPERATOR")
    token = _create_token(operator)

    resp = await test_client.put(
        "/api/v1/annotations/event-rules",
        json={"rules": []},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_events_paginates(test_client, db_session):
    from tests.test_phase7 import _create_user

    admin = await _create_user(db_session, role="ADMIN")
    token = _create_token(admin)

    for i in range(3):
        db_session.add(
            PerceptionEvent(
                event_type="dwell",
                rule_id="dwell_pedestrian_roadside",
                rule_name="Pedestrian dwell",
                track_id=1,
                class_name="person",
                confidence=0.9,
                auto_save=False,
                triggered_at=datetime(2026, 8, 16, 12, i, tzinfo=UTC),
                details={},
            )
        )
    await db_session.commit()

    resp = await test_client.get(
        "/api/v1/annotations/events",
        params={"limit": 2},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["items"][0]["event_type"] == "dwell"
