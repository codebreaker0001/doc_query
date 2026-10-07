import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
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

# NullPool: never reuse a pooled connection across calls. The embedded
# worker runs in a background thread with its own event loop; asyncpg
# connections are loop-bound, and a pooled connection opened under one loop
# breaks when touched from another. No pooling means nothing persists across
# loop boundaries to corrupt. Costs a fresh connection per use, acceptable
# at this traffic scale.
engine = create_async_engine(db_url, connect_args={"ssl": "require"}, poolclass=NullPool)
async_session = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()




