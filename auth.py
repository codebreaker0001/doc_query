import hashlib
import secrets

from fastapi import Header, HTTPException
from sqlalchemy import select

from db import async_session
from models import Tenant


def generate_api_key() -> str:
    return secrets.token_hex(32)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def get_current_tenant(x_api_key: str = Header(...)) -> Tenant:
    api_key_hash = hash_api_key(x_api_key)

    async with async_session() as session:
        tenant = await session.scalar(
            select(Tenant).where(Tenant.api_key_hash == api_key_hash)
        )

    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return tenant
