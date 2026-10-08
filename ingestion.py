import asyncio
import hashlib

import structlog
from sqlalchemy import select

from cache import invalidate_tenant_cache
from chunking import split_into_chunks
from db import tenant_session
from embed import embed_texts
from logging_config import logger
from models import Chunk, Document, IngestionJob, JobStatus


async def process_document(
    job_id: int, tenant_id: int, filename: str, pages: list[str], request_id: str, redis_client_override=None
):
    structlog.contextvars.bind_contextvars(request_id=request_id)
    logger.info("processing_started", job_id=job_id, tenant_id=tenant_id)

    async with tenant_session(tenant_id) as session:
        job = await session.get(IngestionJob, job_id)
        job.status = JobStatus.processing
        await session.commit()

    try:
        full_text = "\n\n".join(pages)
        content_hash = hashlib.sha256(full_text.encode()).hexdigest()
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

            chunks = split_into_chunks(pages)
            chunks_text = [chunk["text"] for chunk in chunks]
            embeddings = embed_texts(chunks_text)

            document = Document(tenant_id=tenant_id, filename=filename, content_hash=content_hash)
            session.add(document)
            await session.flush()
            
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_row = Chunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk["text"],
                    page=chunk["page"],
                    embedding=embedding,
                )
                session.add(chunk_row)


            job = await session.get(IngestionJob, job_id)
            job.status = JobStatus.done
            job.document_id = document.id
            await session.commit()

            await invalidate_tenant_cache(tenant_id, client=redis_client_override)

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


def process_document_sync(job_id: int, tenant_id: int, filename: str, pages: list[str], request_id: str):
    """RQ workers call sync functions; this is the entry point the queue enqueues."""
    import os

    from redis.asyncio import Redis

    from db import engine

    async def run():
        # A dedicated Redis client for this job, never the shared
        # redis_client.py singleton -- that singleton is also used by the
        # main FastAPI event loop (e.g. rate limiting on every request,
        # including the upload request that enqueued this very job).
        # redis.asyncio connections are loop-bound; sharing the singleton
        # across the main thread's loop and this worker thread's loop
        # caused "Future attached to a different loop" errors.
        worker_redis = Redis.from_url(os.environ["REDIS_URL"])
        try:
            await process_document(job_id, tenant_id, filename, pages, request_id, redis_client_override=worker_redis)
        finally:
            # Each call gets its own event loop via asyncio.run(). The DB
            # engine is a module-level singleton; NullPool (see db.py) means
            # it has no pooled connections to leak across loops, but
            # disposing is still cheap insurance. worker_redis is local to
            # this call, so just close it outright.
            await engine.dispose()
            await worker_redis.aclose()

    asyncio.run(run())
