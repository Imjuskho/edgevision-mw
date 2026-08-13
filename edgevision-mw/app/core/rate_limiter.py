from __future__ import annotations

import time
import uuid

from app.core.config import settings
from app.core.dependencies import get_redis


class RateLimitChecker:
    def __init__(self, redis, max_requests: int, window_seconds: int):
        self._redis = redis
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def is_allowed(self, key: str) -> tuple[bool, int]:
        try:
            now = time.time()
            window_start = now - self.window_seconds
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zcard(key)
            pipe.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
            pipe.expire(key, self.window_seconds + 1)
            results = await pipe.execute()

            request_count = results[1]
            if request_count >= self.max_requests:
                oldest_allowed = now - window_start
                return False, int(oldest_allowed)

            return True, 0
        except Exception:
            return True, 0


def _dev_login_limit() -> tuple[int, int]:
    if settings.ENVIRONMENT == "development":
        return 30, 60
    return settings.LOGIN_RATE_LIMIT_MAX, settings.LOGIN_RATE_LIMIT_WINDOW


def _dev_register_limit() -> tuple[int, int]:
    if settings.ENVIRONMENT == "development":
        return 15, 60
    return settings.REGISTER_RATE_LIMIT_MAX, settings.REGISTER_RATE_LIMIT_WINDOW


async def get_login_rate_limit():
    redis = await get_redis()
    max_requests, window_seconds = _dev_login_limit()
    return RateLimitChecker(redis, max_requests=max_requests, window_seconds=window_seconds)


async def get_register_rate_limit():
    redis = await get_redis()
    max_requests, window_seconds = _dev_register_limit()
    return RateLimitChecker(redis, max_requests=max_requests, window_seconds=window_seconds)
