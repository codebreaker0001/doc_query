import hashlib
import json

from redis_client import redis_client

CACHE_TTL_SECONDS = 3600  # 1 hour


def _cache_key(tenant_id: int, question: str) -> str:
    question_hash = hashlib.sha256(question.encode()).hexdigest()
    return f"query_cache:{tenant_id}:{question_hash}"


async def get_cached_answer(tenant_id: int, question: str) -> dict | None:
    key = _cache_key(tenant_id, question)
    cached = await redis_client.get(key)
    if cached is None:
        return None
    return json.loads(cached)


async def set_cached_answer(tenant_id: int, question: str, result: dict):
    key = _cache_key(tenant_id, question)
    await redis_client.set(key, json.dumps(result), ex=CACHE_TTL_SECONDS)


async def invalidate_tenant_cache(tenant_id: int):
    async for key in redis_client.scan_iter(match=f"query_cache:{tenant_id}:*"):
        await redis_client.delete(key)
