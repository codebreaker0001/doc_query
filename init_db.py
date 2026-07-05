import asyncio

from db import Base, engine
import models  # noqa: F401  (import needed so Base knows about Document and Chunk)


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created")


asyncio.run(main())
