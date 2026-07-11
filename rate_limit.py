import time

from fastapi import HTTPException

from redis_client import redis_client

RATE_LIMIT = 30  # max requests allowed per window
WINDOW_SECONDS = 60


async def check_rate_limit(tenant_id: int):
    window = int(time.time() // WINDOW_SECONDS)
    key = f"ratelimit:{tenant_id}:{window}"

    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, WINDOW_SECONDS)

    if count > RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded, try again shortly")
