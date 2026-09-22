"""Idempotency key storage for duplicate-request prevention.

Uses Redis with TTL for key expiry. Falls back to in-memory dict with TTL
tracking and periodic eviction to prevent unbounded memory growth.
"""
import time
from typing import Optional

from app.core.logging import get_logger

logger = get_logger("edgevision.idempotency")

# In-memory fallback: stores {key: (value: str, expiry: float)}
_idempotency_store: dict[str, tuple[str, float]] = {}
IDEMPOTENCY_TTL_SECONDS = 3600  # 1 hour
_MAX_IDEMPOTENCY_SIZE = 10000


def _evict_expired() -> None:
    """Remove expired keys from the in-memory store."""
    now = time.time()
    expired = [k for k, (_, exp) in _idempotency_store.items() if exp <= now]
    for k in expired:
        del _idempotency_store[k]


async def check_idempotency(key: str, ttl: int = IDEMPOTENCY_TTL_SECONDS) -> bool:
    """Check if an idempotency key already exists.

    Returns True if duplicate (request was already processed).
    Returns False if key is new (request should proceed).
    """
    # Try Redis first
    try:
        from app.core.dependencies import get_redis

        redis = await get_redis()
        if redis:
            redis_key = f"idempotency:{key}"
            exists = await redis.exists(redis_key)
            if exists:
                return True
            await redis.setex(redis_key, ttl, "1")
            return False
    except Exception:
        pass

    # Fallback to in-memory with TTL tracking
    now = time.time()
    entry = _idempotency_store.get(key)
    if entry is not None:
        _, expiry = entry
        if expiry > now:
            return True
        # Expired — treat as new key below

    _idempotency_store[key] = ("1", now + ttl)
    _evict_expired()

    if len(_idempotency_store) > _MAX_IDEMPOTENCY_SIZE:
        logger.warning(
            "Idempotency in-memory cache exceeds %d entries — consider enabling Redis",
            _MAX_IDEMPOTENCY_SIZE,
        )

    return False
