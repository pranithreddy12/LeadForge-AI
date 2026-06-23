from __future__ import annotations

import time

import redis

from app.core.config import settings
from app.core.errors import RateLimited

_redis: redis.Redis | None = None


def _client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def hit(key: str, limit: int, window_seconds: int) -> None:
    """Simple fixed-window rate limit. Raises 429 when exceeded."""
    bucket = int(time.time() // window_seconds)
    redis_key = f"rl:{key}:{bucket}"
    pipe = _client().pipeline()
    pipe.incr(redis_key, 1)
    pipe.expire(redis_key, window_seconds + 1)
    count, _ = pipe.execute()
    if count > limit:
        raise RateLimited(retry_after=window_seconds)
