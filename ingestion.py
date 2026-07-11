import hashlib

import structlog
from sqlalchemy import select

from cache import invalidate_tenant_cache
from chunking import split_into_chunks
from db import tenant_session
from embed import embed_texts
from logging_config import logger
from models import Chunk, Document, IngestionJob, JobStatus


async def process_document(job_id: int, tenant_id: int, filename: str, content: str, request_id: str):
    structlog.contextvars.bind_contextvars(request_id=request_id)
    logger.info("processing_started", job_id=job_id, tenant_id=tenant_id)

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
                logger.info("processing_skipped_duplicate", job_id=job_id, document_id=existing.id)
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

        logger.info("processing_finished", job_id=job_id, document_id=document.id, num_chunks=len(chunks_text))

    except Exception as e:
        async with tenant_session(tenant_id) as session:
            job = await session.get(IngestionJob, job_id)
            job.status = JobStatus.failed
            job.error_message = str(e)
            await session.commit()

        logger.error("processing_failed", job_id=job_id, error=str(e))
    finally:
        structlog.contextvars.clear_contextvars()
