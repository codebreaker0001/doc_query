import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
from sqlalchemy import text

@asynccontextmanager
async def tenant_session(tenant_id: int):
    async with async_session() as session:
        await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
        yield session



load_dotenv()

raw_url = os.environ["DATABASE_URL"]
db_url = raw_url.replace("postgresql://", "postgresql+asyncpg://").split("?")[0]

engine = create_async_engine(db_url, connect_args={"ssl": "require"})
async_session = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()




