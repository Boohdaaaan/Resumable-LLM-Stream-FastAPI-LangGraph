import os
from redis.asyncio import Redis

from functools import lru_cache

@lru_cache(maxsize=1)
def get_redis() -> Redis:
    redis = Redis(
        host=os.getenv("REDIS_HOST"),
        port=os.getenv("REDIS_PORT"),
        decode_responses=True,
        username=os.getenv("REDIS_USERNAME", None),
        password=os.getenv("REDIS_PASSWORD", None),
    )
    return redis
