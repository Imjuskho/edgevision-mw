from __future__ import annotations

import json

import httpx
import pytest
from unittest.mock import patch

from app.ai.events import default_rules, rules_from_dicts
from app.models.alert_channel import AlertChannel
from app.services import alerts


def _create_token(user):
    from app.core.security import create_access_token

    return create_access_token(data={"sub": str(user.id), "role": user.role})


def _auth_headers(user):
    return {"Authorization": f"Bearer {_create_token(user)}"}


async def _create_admin(db):
    from tests.test_phase7 import _create_user

    return await _create_user(db, role="ADMIN")


async def _create_annotator(db):
    from tests.test_phase7 import _create_user

    return await _create_user(db, role="ANNOTATOR")


@pytest.mark.asyncio
async def test_default_rules_have_alert_flags(test_client, db_session):
    rules = default_rules()
    by_id = {r.rule_id: r for r in rules}
    assert by_id["dwell_pedestrian_roadside"].alert is True
    assert by_id["dwell_vehicle"].alert is True
    assert by_id["close_approach"].alert is True
    assert by_id["presence_pedestrian"].alert is False

    roundtrip = rules_from_dicts([r.to_dict() for r in rules])
    assert roundtrip[0].alert is True
    raw = [r.to_dict() for r in rules]
    assert "alert" in raw[0]


@pytest.mark.asyncio
async def test_alert_channel_crud_endpoints(test_client, db_session):
    admin = await _create_admin(db_session)
    headers = _auth_headers(admin)

    resp = await test_client.post(
        "/api/v1/annotations/alert-channels",
        json={
            "channel_type": "webhook",
            "name": "Ops Slack webhook",
            "config": {"url": "https://example.com/hookabc"},
            "enabled": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["channel_type"] == "webhook"
    assert data["enabled"] is True
    channel_id = data["id"]

    resp = await test_client.get(
        "/api/v1/annotations/alert-channels",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    ids = [c["id"] for c in resp.json()]
    assert channel_id in ids

    resp = await test_client.patch(
        f"/api/v1/annotations/alert-channels/{channel_id}",
        json={"enabled": False, "name": "Disabled webhook"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["enabled"] is False
    assert resp.json()["name"] == "Disabled webhook"

    resp = await test_client.delete(
        f"/api/v1/annotations/alert-channels/{channel_id}",
        headers=headers,
    )
    assert resp.status_code == 204, resp.text

    resp = await test_client.get(
        "/api/v1/annotations/alert-channels",
        headers=headers,
    )
    assert channel_id not in [c["id"] for c in resp.json()]


@pytest.mark.asyncio
async def test_alert_channel_endpoints_require_admin(test_client, db_session):
    annotator = await _create_annotator(db_session)
    headers = _auth_headers(annotator)

    resp = await test_client.post(
        "/api/v1/annotations/alert-channels",
        json={"channel_type": "webhook", "name": "nope", "config": {}},
        headers=headers,
    )
    assert resp.status_code == 403, resp.text

    resp = await test_client.get(
        "/api/v1/annotations/alert-channels",
        headers=_auth_headers(await _create_admin(db_session)),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_alert_channel_rejects_bad_type(test_client, db_session):
    admin = await _create_admin(db_session)
    resp = await test_client.post(
        "/api/v1/annotations/alert-channels",
        json={"channel_type": "carrier_pigeon", "name": "x", "config": {}},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_alert_channel_not_found(test_client, db_session):
    admin = await _create_admin(db_session)
    missing = "00000000-0000-0000-0000-000000000000"
    resp = await test_client.patch(
        f"/api/v1/annotations/alert-channels/{missing}",
        json={"enabled": False},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_dispatch_webhook_delivers_payload(test_client, db_session):
    channel = await alerts.create_channel(
        db_session,
        channel_type="webhook",
        name="webhook",
        config={"url": "https://example.com/hookedge"},
        enabled=True,
    )
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    event = {"event_id": "evt-1", "event_type": "dwell", "rule_id": "dwell_pedestrian_roadside"}
    rule = {"rule_id": "dwell_pedestrian_roadside", "name": "Pedestrian dwell", "alert": True}

    with patch("app.services.alerts.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = real_async_client(transport=transport)
        results = await alerts.dispatch_event_alert(db_session, event, rule, tenant_id=None)

    assert len(results) == 1
    assert results[0]["delivered"] is True
    assert results[0]["channel_id"] == str(channel.id)
    assert captured["payload"]["event"]["event_id"] == "evt-1"
    assert captured["payload"]["rule"]["alert"] is True

    refreshed = await db_session.get(AlertChannel, channel.id)
    assert refreshed.last_used_at is not None


@pytest.mark.asyncio
async def test_dispatch_webhook_failure_reported(test_client, db_session):
    await alerts.create_channel(
        db_session,
        channel_type="webhook",
        name="bad webhook",
        config={"url": "https://example.com/hookdown"},
        enabled=True,
    )
    event = {"event_id": "evt-2", "event_type": "dwell", "rule_id": "dwell_vehicle"}
    rule = {"rule_id": "dwell_vehicle", "alert": True}

    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    real_async_client = httpx.AsyncClient
    with patch("app.services.alerts.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = real_async_client(transport=transport)
        results = await alerts.dispatch_event_alert(db_session, event, rule, tenant_id=None)

    assert len(results) == 1
    assert results[0]["delivered"] is False
    assert results[0]["status_code"] == 500


@pytest.mark.asyncio
async def test_dispatch_sms_and_push_are_stubs(test_client, db_session):
    await alerts.create_channel(db_session, channel_type="sms", name="sms", config={"phone": "+265..."})
    await alerts.create_channel(db_session, channel_type="push", name="push", config={"push_token": "tok"})
    event = {"event_id": "evt-3", "event_type": "close_approach", "rule_id": "close_approach"}
    rule = {"rule_id": "close_approach", "alert": True}

    results = await alerts.dispatch_event_alert(db_session, event, rule, tenant_id=None)

    assert len(results) == 2
    assert all(r["delivered"] is False for r in results)
    assert {r["channel_type"] for r in results} == {"sms", "push"}
    assert all("not_configured" in r["reason"] for r in results)


@pytest.mark.asyncio
async def test_dispatch_skips_disabled_channels(test_client, db_session):
    await alerts.create_channel(
        db_session,
        channel_type="webhook",
        name="disabled",
        config={"url": "https://example.com/hookx"},
        enabled=False,
    )
    event = {"event_id": "evt-4", "event_type": "dwell", "rule_id": "dwell_pedestrian_roadside"}
    rule = {"rule_id": "dwell_pedestrian_roadside", "alert": True}

    results = await alerts.dispatch_event_alert(db_session, event, rule, tenant_id=None)
    assert results == []


@pytest.mark.asyncio
async def test_dispatch_no_channels_returns_empty(test_client, db_session):
    event = {"event_id": "evt-5", "event_type": "dwell", "rule_id": "dwell_vehicle"}
    rule = {"rule_id": "dwell_vehicle", "alert": True}
    results = await alerts.dispatch_event_alert(db_session, event, rule, tenant_id=None)
    assert results == []


@pytest.mark.asyncio
async def test_alert_channel_rejects_private_webhook_url(test_client, db_session):
    admin = await _create_admin(db_session)
    for url in ["http://127.0.0.1:8000/hook", "http://169.254.169.254/latest/meta-data/"]:
        resp = await test_client.post(
            "/api/v1/annotations/alert-channels",
            json={
                "channel_type": "webhook",
                "name": "ssrf",
                "config": {"url": url},
            },
            headers=_auth_headers(admin),
        )
        assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_alert_channel_rejects_non_http_webhook_url(test_client, db_session):
    admin = await _create_admin(db_session)
    resp = await test_client.post(
        "/api/v1/annotations/alert-channels",
        json={
            "channel_type": "webhook",
            "name": "ftp",
            "config": {"url": "ftp://example.com/hook"},
        },
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_alert_channel_validates_config_per_type(test_client, db_session):
    admin = await _create_admin(db_session)
    headers = _auth_headers(admin)

    resp = await test_client.post(
        "/api/v1/annotations/alert-channels",
        json={"channel_type": "webhook", "name": "no url", "config": {}},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text

    resp = await test_client.post(
        "/api/v1/annotations/alert-channels",
        json={"channel_type": "sms", "name": "no phone", "config": {}},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text

    resp = await test_client.post(
        "/api/v1/annotations/alert-channels",
        json={"channel_type": "push", "name": "short token", "config": {"push_token": "short"}},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text

    resp = await test_client.post(
        "/api/v1/annotations/alert-channels",
        json={"channel_type": "sms", "name": "valid sms", "config": {"phone": "+265888000000"}},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_alert_channel_update_validates_config(test_client, db_session):
    admin = await _create_admin(db_session)
    headers = _auth_headers(admin)
    channel = await alerts.create_channel(
        db_session,
        channel_type="webhook",
        name="hook",
        config={"url": "https://example.com/hook"},
        enabled=True,
    )
    resp = await test_client.patch(
        f"/api/v1/annotations/alert-channels/{channel.id}",
        json={"config": {"url": "http://127.0.0.1:9000/hook"}},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_dispatch_sms_provider_configured(test_client, db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SMS_PROVIDER_URL", "https://example.com/sms")
    await alerts.create_channel(db_session, channel_type="sms", name="sms", config={"phone": "+265888000000"})
    event = {"event_id": "evt-6", "event_type": "close_approach", "rule_id": "close_approach"}
    rule = {"rule_id": "close_approach", "alert": True}
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    with patch("app.services.alerts.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = real_async_client(transport=transport)
        results = await alerts.dispatch_event_alert(db_session, event, rule, tenant_id=None)

    assert len(results) == 1
    assert results[0]["delivered"] is True
    assert captured["payload"]["config"]["phone"] == "+265888000000"
    assert captured["payload"]["alert"]["event"]["event_id"] == "evt-6"
