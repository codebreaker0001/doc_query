import asyncio

from sqlalchemy import text

from db import engine


async def main():
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
        print(result.fetchone())
    await engine.dispose()


asyncio.run(main())
