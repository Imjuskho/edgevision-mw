from __future__ import annotations

from copy import deepcopy
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_settings import UserSettings
from app.models.workspace_settings import WORKSPACE_SETTINGS_KEY, WorkspaceSettings
from app.schemas.user_settings import (
    OperationalSettingsSchema,
    PersonalSettingsSchema,
    UserSettingsPatch,
    default_settings_for_role,
)
from app.services.audit_service import write_audit


def _deep_merge(base: dict, patch: dict) -> dict:
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _normalize_personal(raw: dict | None, role: str) -> dict:
    defaults = default_settings_for_role(role)["personal"]
    if not raw:
        return PersonalSettingsSchema.model_validate(defaults).model_dump()
    personal_raw = raw.get("personal", raw) if isinstance(raw, dict) else {}
    merged = _deep_merge(defaults, personal_raw if isinstance(personal_raw, dict) else {})
    return PersonalSettingsSchema.model_validate(merged).model_dump()


async def _get_workspace_operational_row(db: AsyncSession) -> WorkspaceSettings | None:
    result = await db.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.singleton_key == WORKSPACE_SETTINGS_KEY)
    )
    return result.scalar_one_or_none()


async def get_workspace_operational(db: AsyncSession) -> dict:
    row = await _get_workspace_operational_row(db)
    defaults = default_settings_for_role("ADMIN")["operational"]
    if not row or not row.operational_json:
        return OperationalSettingsSchema.model_validate(defaults).model_dump()
    merged = _deep_merge(defaults, row.operational_json)
    return OperationalSettingsSchema.model_validate(merged).model_dump()


async def get_user_settings(db: AsyncSession, user_id: UUID, role: str) -> dict:
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    row = result.scalar_one_or_none()
    personal = _normalize_personal(row.settings_json if row else None, role)
    operational = await get_workspace_operational(db)
    return {"personal": personal, "operational": operational}


async def patch_user_settings(
    db: AsyncSession,
    user_id: UUID,
    role: str,
    patch: UserSettingsPatch,
    *,
    allow_operational: bool,
    actor_ip: str | None = None,
) -> dict:
    personal = _normalize_personal(None, role)

    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    user_row = result.scalar_one_or_none()
    if user_row:
        personal = _normalize_personal(user_row.settings_json, role)

    if patch.personal:
        personal = _deep_merge(personal, patch.personal.model_dump(exclude_unset=True))
        personal = PersonalSettingsSchema.model_validate(personal).model_dump()

    operational = await get_workspace_operational(db)

    if patch.operational:
        if not allow_operational:
            raise PermissionError("Operational settings require ADMIN role")
        before = deepcopy(operational)
        operational = _deep_merge(operational, patch.operational.model_dump(exclude_unset=True))
        operational = OperationalSettingsSchema.model_validate(operational).model_dump()

        ws_row = await _get_workspace_operational_row(db)
        if ws_row:
            ws_row.operational_json = operational
        else:
            db.add(
                WorkspaceSettings(
                    singleton_key=WORKSPACE_SETTINGS_KEY,
                    operational_json=operational,
                )
            )

        await write_audit(
            db,
            event_type="settings.operational_updated",
            severity="INFO",
            actor_id=user_id,
            actor_type="user",
            resource_type="workspace_settings",
            resource_id=user_id,
            details={"before": before, "after": operational},
            ip_address=actor_ip,
        )

    stored = {"personal": personal}
    if user_row:
        user_row.settings_json = stored
    else:
        db.add(UserSettings(user_id=user_id, settings_json=stored))

    await db.commit()
    return {"personal": personal, "operational": operational}
