"""Admin API for perception-event alert delivery channels."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.logging import get_logger
from app.core.tenant import get_current_tenant_id
from app.models.alert_channel import VALID_CHANNEL_TYPES
from app.services import alerts

logger = get_logger("edgevision.alerts_api")

alerts_router = APIRouter(prefix="/annotations/alert-channels", tags=["Alert Channels"])


class WebhookChannelConfig(BaseModel):
    url: HttpUrl = Field(..., description="HTTP(S) callback URL")
    headers: dict[str, str] = Field(default_factory=dict, description="Extra request headers")
    secret: str | None = Field(default=None, description="Optional shared secret for HMAC signing")


class SmsChannelConfig(BaseModel):
    phone: str = Field(..., min_length=7, max_length=20, description="E.164 recipient phone number")
    provider: str | None = Field(default=None, description="Optional SMS provider identifier")


class PushChannelConfig(BaseModel):
    push_token: str = Field(..., min_length=8, max_length=512, description="Device push token")
    provider: str | None = Field(default=None, description="Optional push provider identifier")


def _build_config_model(channel_type: str | None, config: dict | None) -> dict:
    """Coerce a free-form config dict into its per-type model (empty for unknown types)."""
    if not isinstance(config, dict) or channel_type is None:
        return config
    if channel_type == "webhook":
        return WebhookChannelConfig(**config)
    if channel_type == "sms":
        return SmsChannelConfig(**config)
    if channel_type == "push":
        return PushChannelConfig(**config)
    return config


class AlertChannelCreate(BaseModel):
    channel_type: Literal["webhook", "sms", "push"] = Field(..., description="Delivery channel type")
    name: str = Field(..., min_length=1, max_length=120, description="Human-readable channel name")
    config: WebhookChannelConfig | SmsChannelConfig | PushChannelConfig | dict = Field(
        default_factory=dict, description="Channel-specific config (url, phone, push_token, …)"
    )
    enabled: bool = Field(default=True, description="Whether the channel is active")

    @model_validator(mode="before")
    @classmethod
    def _typed_config(cls, values: dict) -> dict:
        values["config"] = _build_config_model(values.get("channel_type"), values.get("config"))
        return values


class AlertChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    config: WebhookChannelConfig | SmsChannelConfig | PushChannelConfig | dict | None = Field(default=None)
    enabled: bool | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _typed_config(cls, values: dict) -> dict:
        if values.get("config") is not None:
            values["config"] = _build_config_model(values.get("channel_type"), values.get("config"))
        return values


class AlertChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel_type: str
    name: str
    config: dict
    enabled: bool
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


@alerts_router.get("", response_model=list[AlertChannelResponse])
async def list_alert_channels(
    user: dict = Depends(require_role(["ADMIN", "OPERATOR"])),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = get_current_tenant_id()
    return await alerts.list_channels(db, tenant_id=tenant_id)


@alerts_router.post("", response_model=AlertChannelResponse, status_code=201)
async def create_alert_channel(
    body: AlertChannelCreate,
    user: dict = Depends(require_role(["ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    config = body.config.model_dump(mode="json") if isinstance(body.config, BaseModel) else body.config
    try:
        return await alerts.create_channel(
            db,
            channel_type=body.channel_type,
            name=body.name,
            config=config,
            enabled=body.enabled,
            tenant_id=get_current_tenant_id(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@alerts_router.patch("/{channel_id}", response_model=AlertChannelResponse)
async def update_alert_channel(
    channel_id: UUID,
    body: AlertChannelUpdate,
    user: dict = Depends(require_role(["ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    channel = await alerts.get_channel(db, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Alert channel not found")
    config = body.config.model_dump(mode="json") if isinstance(body.config, BaseModel) else body.config
    try:
        return await alerts.update_channel(
            db,
            channel,
            name=body.name,
            config=config,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@alerts_router.delete("/{channel_id}", status_code=204)
async def delete_alert_channel(
    channel_id: UUID,
    user: dict = Depends(require_role(["ADMIN"])),
    db: AsyncSession = Depends(get_db),
):
    channel = await alerts.get_channel(db, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Alert channel not found")
    await alerts.delete_channel(db, channel)
