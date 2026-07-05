import asyncio

from sqlalchemy import text

from db import async_session  # note: plain session, no tenant_session — no tenant set


async def main():
    async with async_session() as session:
        result = await session.execute(text("SELECT count(*) FROM documents"))
        print("Documents visible with no tenant set:", result.scalar())


asyncio.run(main())
