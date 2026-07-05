import asyncio

from db import Base, engine
import models  # noqa: F401  (import needed so Base knows about Tenant, Document, and Chunk)


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Tables dropped and recreated")


asyncio.run(main())
