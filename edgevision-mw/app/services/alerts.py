"""Alert channel CRUD and outbound delivery for perception events.

Webhooks POST a JSON envelope to the configured URL.  SMS and push adapters
are structured-log stubs (no provider credentials exist in this deployment),
so deliveries on those channels are reported as ``not_configured`` rather than
failing silently.
"""

from __future__ import annotations

import ipaddress
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.alert_channel import VALID_CHANNEL_TYPES, AlertChannel

logger = get_logger("edgevision.alerts")

WEBHOOK_TIMEOUT_S = 10.0


def assert_safe_webhook_url(url: str) -> str:
    """Reject webhook URLs that would target loopback, private, or link-local
    destinations (SSRF guard).  Raises ValueError for unsafe or unresolvable URLs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("webhook url must use http or https scheme")
    host = parsed.hostname
    if not host:
        raise ValueError("webhook url must include a hostname")
    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError(f"webhook url host does not resolve: {host}")
    for family, _socktype, _proto, _canonname, sockaddr in resolved:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"webhook url resolves to a disallowed address: {ip}")
    return url


def validate_channel_config(channel_type: str, config: dict | None) -> dict:
    """Per-type validation of AlertChannel config.  Raises ValueError on invalid config."""
    config = config or {}
    if channel_type == "webhook":
        url = config.get("url")
        if not url:
            raise ValueError("webhook channel requires config.url")
        assert_safe_webhook_url(str(url))
    elif channel_type == "sms":
        if not config.get("phone"):
            raise ValueError("sms channel requires config.phone")
    elif channel_type == "push":
        if not config.get("push_token"):
            raise ValueError("push channel requires config.push_token")
    elif channel_type not in VALID_CHANNEL_TYPES:
        raise ValueError(f"Invalid channel_type: {channel_type}; choose from {sorted(VALID_CHANNEL_TYPES)}")
    return config


async def list_channels(db: AsyncSession, *, tenant_id: UUID | None = None) -> list[AlertChannel]:
    result = await db.execute(
        select(AlertChannel).order_by(AlertChannel.created_at)
    )
    channels = list(result.scalars().all())
    if tenant_id is not None:
        return [c for c in channels if c.tenant_id is None or c.tenant_id == tenant_id]
    return [c for c in channels if c.tenant_id is None]


async def get_channel(db: AsyncSession, channel_id: UUID) -> AlertChannel | None:
    return await db.get(AlertChannel, channel_id)


async def create_channel(
    db: AsyncSession,
    *,
    channel_type: str,
    name: str,
    config: dict | None = None,
    enabled: bool = True,
    tenant_id: UUID | None = None,
) -> AlertChannel:
    if channel_type not in VALID_CHANNEL_TYPES:
        raise ValueError(f"Invalid channel_type: {channel_type}; choose from {sorted(VALID_CHANNEL_TYPES)}")
    config = validate_channel_config(channel_type, config)
    channel = AlertChannel(
        channel_type=channel_type,
        name=name,
        config=config,
        enabled=enabled,
        tenant_id=tenant_id,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


async def update_channel(
    db: AsyncSession,
    channel: AlertChannel,
    *,
    name: str | None = None,
    config: dict | None = None,
    enabled: bool | None = None,
) -> AlertChannel:
    if name is not None:
        channel.name = name
    if config is not None:
        channel.config = validate_channel_config(channel.channel_type, config)
    if enabled is not None:
        channel.enabled = enabled
    await db.commit()
    await db.refresh(channel)
    return channel


async def delete_channel(db: AsyncSession, channel: AlertChannel) -> None:
    await db.delete(channel)
    await db.commit()


def build_alert_payload(event: dict, rule: dict) -> dict:
    return {
        "source": "edgevision",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "rule": rule,
    }


async def _deliver_webhook(config: dict, payload: dict) -> dict:
    url = config.get("url")
    if not url:
        return {"delivered": False, "reason": "missing_url"}
    try:
        timeout = httpx.Timeout(WEBHOOK_TIMEOUT_S)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
        ok = 200 <= response.status_code < 400
        return {"delivered": ok, "status_code": response.status_code}
    except Exception as exc:
        logger.warning("alert_webhook_failed", error=str(exc))
        return {"delivered": False, "reason": "request_failed", "error": str(exc)}


async def _deliver_sms(config: dict, payload: dict) -> dict:
    logger.info("alert_deliver attempt type=sms phone=%s", config.get("phone"))
    provider_url = settings.SMS_PROVIDER_URL
    if not provider_url:
        logger.warning(
            "SMS delivery attempted but provider not configured. Alert channel: %s",
            config.get("phone"),
        )
        return {"delivered": False, "reason": "sms_provider_not_configured", "retry_scheduled": False}
    result = await _post_provider(provider_url, config, payload)
    if result.get("delivered"):
        logger.info("sms_delivered phone=%s status=%s", config.get("phone"), result.get("status_code"))
    else:
        logger.warning("sms_delivery_failed phone=%s reason=%s", config.get("phone"), result.get("reason"))
    return result


async def _deliver_push(config: dict, payload: dict) -> dict:
    logger.info("alert_deliver attempt type=push token_present=%s", bool(config.get("push_token")))
    provider_url = settings.PUSH_PROVIDER_URL
    if not provider_url:
        logger.warning(
            "Push delivery attempted but provider not configured. Alert channel: %s",
            config.get("push_token"),
        )
        return {"delivered": False, "reason": "push_provider_not_configured", "retry_scheduled": False}
    result = await _post_provider(provider_url, config, payload)
    if result.get("delivered"):
        logger.info("push_delivered token_present=%s status=%s", bool(config.get("push_token")), result.get("status_code"))
    else:
        logger.warning("push_delivery_failed token_present=%s reason=%s", bool(config.get("push_token")), result.get("reason"))
    return result


async def _post_provider(provider_url: str, config: dict, payload: dict) -> dict:
    try:
        timeout = httpx.Timeout(WEBHOOK_TIMEOUT_S)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(provider_url, json={"config": config, "alert": payload})
        ok = 200 <= response.status_code < 400
        return {"delivered": ok, "status_code": response.status_code}
    except Exception as exc:
        logger.warning("alert_provider_failed", provider=provider_url, error=str(exc))
        return {"delivered": False, "reason": "request_failed", "error": str(exc)}


_ADAPTERS: dict[str, Any] = {
    "webhook": _deliver_webhook,
    "sms": _deliver_sms,
    "push": _deliver_push,
}


async def dispatch_event_alert(
    db: AsyncSession,
    event: dict,
    rule: dict,
    *,
    tenant_id: UUID | None = None,
) -> list[dict]:
    """Deliver an event alert across all enabled channels.

    Returns a per-channel delivery result list; ``delivered`` is True only for
    channels that actually succeeded.
    """
    channels = await list_channels(db, tenant_id=tenant_id)
    if not channels:
        return []
    payload = build_alert_payload(event, rule)
    results: list[dict] = []
    for channel in channels:
        if not channel.enabled:
            continue
        adapter = _ADAPTERS.get(channel.channel_type)
        if adapter is None:
            continue
        result = await adapter(channel.config, payload)
        result["channel_id"] = str(channel.id)
        result["channel_type"] = channel.channel_type
        result["name"] = channel.name
        channel.last_used_at = datetime.now(timezone.utc)
        results.append(result)
    await db.commit()
    return results
