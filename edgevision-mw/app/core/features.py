from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.settings_service import get_workspace_operational
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role


async def _assert_feature_enabled(db: AsyncSession, user: dict, feature_key: str) -> None:
    if user.get("role") == "ADMIN":
        return
    operational = await get_workspace_operational(db)
    features = operational.get("features", {})
    if not features.get(feature_key, True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Feature '{feature_key}' is disabled for this workspace",
        )


def require_feature(feature_key: str):
    """Block API access when an operational feature flag is disabled."""

    async def checker(
        user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        await _assert_feature_enabled(db, user, feature_key)
        return user

    return checker


def require_role_and_feature(roles: list[str], feature_key: str):
    """Combine RBAC with workspace feature-flag enforcement."""

    async def checker(
        user: dict = Depends(require_role(roles)),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        await _assert_feature_enabled(db, user, feature_key)
        return user

    return checker
