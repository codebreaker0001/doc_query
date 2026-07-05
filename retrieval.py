from db import tenant_session
from embed import embed_texts
from models import Chunk, Document
from sqlalchemy import select


async def retrieve_relevant_chunks(query: str, tenant_id: int, top_k: int = 3) -> list[str]:
    query_embedding = embed_texts([query])[0]

    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(Chunk.content)
            .join(Document)
            .where(Document.tenant_id == tenant_id)
            .order_by(Chunk.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
        return [row[0] for row in result]
