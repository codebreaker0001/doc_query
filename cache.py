import hashlib
import json

from redis_client import redis_client

CACHE_TTL_SECONDS = 3600  # 1 hour


def _cache_key(tenant_id: int, question: str, document_id: int | None = None) -> str:
    question_hash = hashlib.sha256(question.encode()).hexdigest()
    scope = document_id if document_id is not None else "all"
    return f"query_cache:{tenant_id}:{scope}:{question_hash}"


async def get_cached_answer(tenant_id: int, question: str, document_id: int | None = None) -> dict | None:
    key = _cache_key(tenant_id, question, document_id)
    cached = await redis_client.get(key)
    if cached is None:
        return None
    return json.loads(cached)


async def set_cached_answer(tenant_id: int, question: str, result: dict, document_id: int | None = None):
    key = _cache_key(tenant_id, question, document_id)
    await redis_client.set(key, json.dumps(result), ex=CACHE_TTL_SECONDS)


async def invalidate_tenant_cache(tenant_id: int):
    async for key in redis_client.scan_iter(match=f"query_cache:{tenant_id}:*"):
        await redis_client.delete(key)
