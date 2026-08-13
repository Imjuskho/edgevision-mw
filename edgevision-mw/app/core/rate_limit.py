"""Sliding window rate limiter — Redis-backed with in-memory fallback."""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class RateLimitRule:
    max_requests: int
    window_seconds: int


RATE_LIMIT_RULES: dict[str, RateLimitRule] = {
    "/auth/login": RateLimitRule(max_requests=5, window_seconds=60),
    "/auth/register": RateLimitRule(max_requests=3, window_seconds=60),
    "/nodes/heartbeat": RateLimitRule(max_requests=60, window_seconds=60),
    "/ingest/batch": RateLimitRule(max_requests=10, window_seconds=60),
    "/jobs/assign": RateLimitRule(max_requests=30, window_seconds=60),
    "/datasets/search": RateLimitRule(max_requests=100, window_seconds=60),
    "/datasets/quotes": RateLimitRule(max_requests=20, window_seconds=60),
    "/exports": RateLimitRule(max_requests=5, window_seconds=60),
}

_HEALTH_PATH = "/health"

# In-memory fallback store (per-worker)
_mem_store: dict[str, list[float]] = defaultdict(list)


def _resolve_key(request: Request, path_pattern: str) -> str:
    client_ip = request.client.host if request.client else "unknown"

    if path_pattern == "/nodes/heartbeat":
        node_id = request.headers.get("X-Node-ID", "anon")
        return f"rl:heartbeat:{node_id}"

    if path_pattern in ("/datasets/search", "/datasets/quotes", "/exports"):
        api_key = request.headers.get("X-API-Key")
        if api_key:
            h = hashlib.sha256(api_key.encode()).hexdigest()[:16]
            return f"rl:buyer:{h}:{path_pattern}"
        return f"rl:ip:{client_ip}:{path_pattern}"

    if path_pattern == "/jobs/assign":
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            h = hashlib.sha256(auth[7:].encode()).hexdigest()[:16]
            return f"rl:annotator:{h}"
        return f"rl:ip:{client_ip}:{path_pattern}"

    return f"rl:ip:{client_ip}:{path_pattern}"


def _check_memory(key: str, rule: RateLimitRule) -> JSONResponse | None:
    now = time.time()
    cutoff = now - rule.window_seconds
    timestamps = _mem_store[key]
    _mem_store[key] = [t for t in timestamps if t > cutoff]
    if len(_mem_store[key]) >= rule.max_requests:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
            headers={"Retry-After": str(rule.window_seconds)},
        )
    _mem_store[key].append(now)
    return None


async def _check_redis(key: str, rule: RateLimitRule) -> JSONResponse | None:
    from app.core.dependencies import _redis_client

    if _redis_client is None:
        return None

    now = time.time()
    window_start = now - rule.window_seconds
    pipe = _redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, rule.window_seconds + 1)
    results = await pipe.execute()

    request_count = results[2]
    if request_count > rule.max_requests:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
            headers={"Retry-After": str(rule.window_seconds)},
        )
    return None


async def check_rate_limit(request: Request) -> JSONResponse | None:
    path = request.url.path

    if path == _HEALTH_PATH:
        return None

    matched_rule: RateLimitRule | None = None
    matched_pattern: str | None = None
    for pattern, rule in RATE_LIMIT_RULES.items():
        if pattern in path:
            matched_rule = rule
            matched_pattern = pattern
            break

    if matched_rule is None:
        return None

    key = _resolve_key(request, matched_pattern)

    try:
        result = await _check_redis(key, matched_rule)
        if result is not None:
            return result
    except Exception:
        pass

    return _check_memory(key, matched_rule)
