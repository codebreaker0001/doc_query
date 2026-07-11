import hashlib

from sqlalchemy import select

from chunking import split_into_chunks
from db import tenant_session
from embed import embed_texts
from models import Chunk, Document, IngestionJob, JobStatus
from cache import invalidate_tenant_cache

async def process_document(job_id: int, tenant_id: int, filename: str, content: str):
    async with tenant_session(tenant_id) as session:
        job = await session.get(IngestionJob, job_id)
        job.status = JobStatus.processing
        await session.commit()

    try:
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        async with tenant_session(tenant_id) as session:
            existing = await session.scalar(
                select(Document).where(
                    Document.content_hash == content_hash,
                    Document.tenant_id == tenant_id,
                )
            )
            if existing is not None:
                job = await session.get(IngestionJob, job_id)
                job.status = JobStatus.done
                job.document_id = existing.id
                await session.commit()
                return

            chunks_text = split_into_chunks(content)
            embeddings = embed_texts(chunks_text)

            document = Document(tenant_id=tenant_id, filename=filename, content_hash=content_hash)
            session.add(document)
            await session.flush()

            for index, (chunk_text, embedding) in enumerate(zip(chunks_text, embeddings)):
                chunk = Chunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk_text,
                    embedding=embedding,
                )
                session.add(chunk)

            job = await session.get(IngestionJob, job_id)
            job.status = JobStatus.done
            job.document_id = document.id
            await session.commit()
            await invalidate_tenant_cache(tenant_id)


    except Exception as e:
        async with tenant_session(tenant_id) as session:
            job = await session.get(IngestionJob, job_id)
            job.status = JobStatus.failed
            job.error_message = str(e)
            await session.commit()
