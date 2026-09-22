from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import authenticate_user, create_api_key, create_user
from app.auth.settings_service import get_user_settings, patch_user_settings
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.logging import get_logger, trace
from app.core.rate_limiter import get_login_rate_limit, get_register_rate_limit
from app.core.security import create_access_token
from app.models.buyer import User
from app.schemas.audit import AuditLogListResponse
from app.schemas.auth import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyResponse,
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.schemas.user_settings import UserSettingsPatch, UserSettingsResponse
from app.services.audit_service import list_audit_logs

auth_router = APIRouter(prefix="/auth", tags=["Auth"])
logger = get_logger("edgevision.api.auth")


@auth_router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: Request,
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    rate_limit=Depends(get_register_rate_limit),
):
    trace_id = str(uuid4())
    client_ip = request.client.host if request.client else "unknown"
    trace(logger, "register_start", trace_id=trace_id, email=body.email, client_ip=client_ip)
    allowed, retry_after = await rate_limit.is_allowed(f"register:{client_ip}")
    if not allowed:
        trace(logger, "register_rate_limited", trace_id=trace_id, email=body.email, client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        user_payload = body.model_dump()
        # Public self-registration always gets the studio annotator role.
        user_payload.pop("role", None)
        user = await create_user(db, user_payload)
    except ValueError as exc:
        trace(logger, "register_conflict", trace_id=trace_id, email=body.email, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    trace(logger, "register_success", trace_id=trace_id, user_id=str(user.id), email=user.email)
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        organization=user.organization,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@auth_router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    rate_limit=Depends(get_login_rate_limit),
):
    trace_id = str(uuid4())
    client_ip = request.client.host if request.client else "unknown"
    trace(logger, "login_start", trace_id=trace_id, email=body.email, client_ip=client_ip)
    allowed, retry_after = await rate_limit.is_allowed(f"login:{client_ip}")
    if not allowed:
        trace(logger, "login_rate_limited", trace_id=trace_id, email=body.email, client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    user = await authenticate_user(db, body.email, body.password)
    if user is None:
        trace(
            logger,
            "login_failed",
            trace_id=trace_id,
            email=body.email,
            client_ip=client_ip,
            reason="invalid_credentials",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(data={"sub": str(user.id), "role": user.role, "email": user.email})
    trace(logger, "login_success", trace_id=trace_id, user_id=str(user.id), email=user.email, role=user.role)
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@auth_router.post(
    "/api-keys",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_key(
    body: APIKeyCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raw_key, api_key = await create_api_key(db, UUID(user["sub"]), body.model_dump())
    return APIKeyCreateResponse(
        id=api_key.id,
        key_id=api_key.key_id,
        name=api_key.name,
        key=raw_key,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@auth_router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_keys(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.models.buyer import BuyerApiKey

    result = await db.execute(
        select(BuyerApiKey).where(
            BuyerApiKey.user_id == UUID(user["sub"]),
            BuyerApiKey.is_active == True,  # noqa: E712
        )
    )
    keys = result.scalars().all()
    return [
        APIKeyResponse(
            id=k.id,
            key_id=k.key_id,
            name=k.name,
            scopes=k.scopes,
            created_at=k.created_at,
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@auth_router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_key(
    key_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.models.buyer import BuyerApiKey

    result = await db.execute(
        select(BuyerApiKey).where(
            BuyerApiKey.key_id == key_id,
            BuyerApiKey.user_id == UUID(user["sub"]),
            BuyerApiKey.is_active == True,  # noqa: E712
        )
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    api_key.is_active = False
    await db.commit()


@auth_router.get("/me", response_model=UserResponse)
async def get_me(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == UUID(user["sub"])))
    db_user = result.scalar_one_or_none()
    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse(
        id=db_user.id,
        email=db_user.email,
        full_name=db_user.full_name,
        organization=db_user.organization,
        role=db_user.role,
        is_active=db_user.is_active,
        created_at=db_user.created_at,
    )


@auth_router.get("/users", response_model=list[UserResponse])
async def list_users(
    role: str | None = None,
    user: dict = Depends(require_role(["ADMIN", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    """List active users for admin assignment (optional role filter)."""
    query = select(User).where(User.is_active.is_(True))
    if role:
        query = query.where(User.role == role.upper())
    query = query.order_by(User.full_name, User.email)
    result = await db.execute(query)
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            organization=u.organization,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in result.scalars().all()
    ]


@auth_router.get("/me/settings", response_model=UserSettingsResponse)
async def get_my_settings(
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = user.get("role", "ANNOTATOR")
    settings = await get_user_settings(db, UUID(user["sub"]), role)
    return UserSettingsResponse(
        personal=settings["personal"],
        operational=settings["operational"],
        role=role,
        synced=True,
    )


@auth_router.patch("/me/settings", response_model=UserSettingsResponse)
async def update_my_settings(
    request: Request,
    body: UserSettingsPatch,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = user.get("role", "ANNOTATOR")
    client_ip = request.client.host if request.client else None
    allow_operational = role == "ADMIN"
    try:
        settings = await patch_user_settings(
            db,
            UUID(user["sub"]),
            role,
            body,
            allow_operational=allow_operational,
            actor_ip=client_ip,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return UserSettingsResponse(
        personal=settings["personal"],
        operational=settings["operational"],
        role=role,
        synced=True,
    )


@auth_router.get("/audit-logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    event_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(require_role(["ADMIN", "QA"])),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_audit_logs(
        db,
        event_type=event_type,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )
    return AuditLogListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
