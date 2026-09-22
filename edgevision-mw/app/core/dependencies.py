from datetime import UTC

import minio
import redis.asyncio as aioredis
from fastapi import Depends, Header, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import (
    CircuitBreakerOpenError,
    minio_circuit_breaker,
    redis_circuit_breaker,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token, verify_node_signature

_bearer_scheme = HTTPBearer(auto_error=False)

_redis_client: aioredis.Redis | None = None
_minio_client: minio.Minio | None = None


async def init_connections():
    global _redis_client, _minio_client
    _redis_client = aioredis.from_url(
        settings.REDIS_URL,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
    )
    _minio_client = minio.Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


async def close_connections():
    global _redis_client, _minio_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
    _minio_client = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def require_role(roles: list[str]):
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role")
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' not in required roles: {roles}",
            )
        return user

    return role_checker


async def get_redis() -> aioredis.Redis:
    if _redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not connected",
        )
    if not redis_circuit_breaker.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis circuit breaker is OPEN — too many failures",
        )
    return _redis_client


async def ping_redis() -> bool:
    """Health-check ping wrapped in circuit breaker."""
    client = await get_redis()
    try:
        await redis_circuit_breaker.acall(client.ping)
        return True
    except CircuitBreakerOpenError:
        return False
    except Exception:
        return False


async def get_minio_client() -> minio.Minio:
    if _minio_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MinIO not connected",
        )
    if not minio_circuit_breaker.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MinIO circuit breaker is OPEN — too many failures",
        )
    return _minio_client


def get_minio_client_sync() -> minio.Minio:
    """Sync version for Celery workers where init_connections() is not called.

    Creates a new MinIO client on first call within the worker process and
    caches it for reuse across multiple task invocations.
    """
    if not minio_circuit_breaker.is_available():
        from app.core.circuit_breaker import CircuitBreakerOpenError

        raise CircuitBreakerOpenError("MinIO circuit breaker is OPEN — too many failures")
    global _minio_client
    if _minio_client is None:
        mc = minio.Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        _minio_client = mc
    return _minio_client


async def require_node_auth(
    x_node_id: str = Header(...),
    x_node_timestamp: str = Header(...),
    x_node_signature: str = Header(...),
    x_node_public_key: str = Header(...),
) -> dict:
    import base64
    from datetime import datetime

    try:
        # Timestamp freshness check (replay protection)
        try:
            node_time = datetime.fromisoformat(x_node_timestamp)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid timestamp format",
            )

        now = datetime.now(UTC)
        if node_time.tzinfo is None:
            node_time = node_time.replace(tzinfo=UTC)
        if abs((now - node_time).total_seconds()) > 60:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Expired node timestamp - possible replay attack",
            )

        message = f"{x_node_id}:{x_node_timestamp}".encode()
        signature = base64.b64decode(x_node_signature)
        public_key = base64.b64decode(x_node_public_key)

        if not verify_node_signature(public_key, message, signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid node signature",
            )

        return {
            "node_id": x_node_id,
            "timestamp": x_node_timestamp,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node authentication headers",
        )


async def get_current_buyer(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.auth.service import verify_api_key

    user = await verify_api_key(db, x_api_key)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )
    return {"sub": str(user.id), "role": user.role, "email": user.email}


async def get_current_buyer_or_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if x_api_key:
        from app.auth.service import verify_api_key

        user = await verify_api_key(db, x_api_key)
        if user is not None:
            return {"sub": str(user.id), "role": user.role, "email": user.email}

    if credentials:
        try:
            payload = decode_access_token(credentials.credentials)
            user_id: str | None = payload.get("sub")
            if user_id is not None:
                return payload
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid X-API-Key or Bearer token",
    )


async def get_current_user_ws(websocket: WebSocket) -> dict | None:
    """Authenticate a WebSocket connection via Bearer token in query params or Authorization header."""
    token = websocket.query_params.get("token") or websocket.query_params.get("studio_token") or ""
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ")

    if not token:
        return None

    try:
        payload = decode_access_token(token)
        if payload.get("sub") is not None:
            return payload
    except Exception:
        pass
    return None
