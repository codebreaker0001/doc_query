from db import tenant_session
from embed import embed_texts
from models import Chunk, Document
from reranker import rerank
from sqlalchemy import select


async def retrieve_relevant_chunks(
    query: str,
    tenant_id: int,
    document_id: int | None = None,
    top_k: int = 3,
    candidate_k: int = 15,
) -> list[str]:
    query_embedding = embed_texts([query])[0]

    async with tenant_session(tenant_id) as session:
        stmt = select(Chunk.content).join(Document).where(Document.tenant_id == tenant_id)

        if document_id is not None:
            stmt = stmt.where(Document.id == document_id)

        stmt = stmt.order_by(Chunk.embedding.cosine_distance(query_embedding)).limit(candidate_k)
        result = await session.execute(stmt)
        candidates = [row[0] for row in result]

    return rerank(query, candidates, top_k=top_k)
