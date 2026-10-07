import os
import threading
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, File, HTTPException, Request , UploadFile
from pydantic import BaseModel, field_validator
from rq.worker import SimpleWorker
from rq.timeouts import TimerDeathPenalty

from auth import generate_api_key, hash_api_key, get_current_tenant, get_rate_limited_tenant
from cache import get_cached_answer, set_cached_answer
from db import async_session, tenant_session
from ingestion import process_document_sync
from job_queue import job_queue, redis_conn
from llm import generate_answer
from logging_config import configure_logging, logger
from models import IngestionJob, JobStatus, Tenant , Document
from retrieval import retrieve_relevant_chunks
from pdf_extraction import extract_pages_from_pdf
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
configure_logging()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB


class ThreadWorker(SimpleWorker):
    # signal.signal() only works in the main thread of the main interpreter.
    # This worker runs in a background thread, so (1) skip signal-based
    # shutdown entirely -- it's a daemon thread, it just dies with the
    # process -- and (2) use RQ's thread-safe TimerDeathPenalty (threading
    # .Timer-based) for per-job timeouts instead of the default
    # UnixSignalDeathPenalty, which also calls signal.signal() and crashes
    # every job the same way.
    death_penalty_class = TimerDeathPenalty

    def _install_signal_handlers(self):
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Render's free tier has no separate worker process, and a subprocess
    # worker loads a second full copy of torch/transformers in memory --
    # too much for the 512MB free-tier limit. A thread shares this process's
    # memory (one copy of the models), which is why we're back to this
    # despite the earlier hang -- that was caused by the DB engine pooling
    # connections across event loops in different threads, fixed now via
    # NullPool in db.py (see the comment there), not by avoiding threads.
    if os.environ.get("ENABLE_EMBEDDED_WORKER") == "true":
        thread = threading.Thread(
            target=lambda: ThreadWorker([job_queue], connection=redis_conn).work(),
            daemon=True,
        )
        thread.start()
        logger.info("embedded_worker_started")
    yield
    if worker_process:
        worker_process.terminate()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    structlog.contextvars.bind_contextvars(request_id=request_id)

    logger.info("request_started", method=request.method, path=request.url.path)
    response = await call_next(request)
    logger.info("request_finished", status_code=response.status_code)

    structlog.contextvars.clear_contextvars()
    return response





class QueryRequest(BaseModel):
    question: str
    document_id: int | None = None


class TenantSignupRequest(BaseModel):
    name: str


@app.post("/tenants")
async def create_tenant(request: TenantSignupRequest):
    raw_key = generate_api_key()
    api_key_hash = hash_api_key(raw_key)

    async with async_session() as session:
        tenant = Tenant(name=request.name, api_key_hash=api_key_hash)
        session.add(tenant)
        await session.commit()

    logger.info("tenant_created", tenant_id=tenant.id)
    return {"tenant_id": tenant.id, "api_key": raw_key}


@app.post("/documents", status_code=202)
async def upload_document(
    http_request: Request,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_rate_limited_tenant),

):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content_length = http_request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    file_bytes = await file.read()
    pages = extract_pages_from_pdf(file_bytes)

    if not any(page.strip() for page in pages):
        raise HTTPException(status_code=400, detail="PDF contains no extractable text")

    async with tenant_session(tenant.id) as session:
        job = IngestionJob(tenant_id=tenant.id, status=JobStatus.pending)
        session.add(job)
        await session.commit()

    logger.info("job_created", job_id=job.id, tenant_id=tenant.id)

    job_queue.enqueue(
        process_document_sync, job.id, tenant.id, file.filename, pages, http_request.state.request_id
    )


    return {"job_id": job.id, "status": job.status, "filename": file.filename}

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: int, tenant: Tenant = Depends(get_current_tenant)):
    async with tenant_session(tenant.id) as session:
        job = await session.get(IngestionJob, job_id)

    if job is None or job.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.id,
        "status": job.status,
        "document_id": job.document_id,
        "error_message": job.error_message,
    }


@app.post("/query")
async def query_documents(request: QueryRequest, tenant: Tenant = Depends(get_rate_limited_tenant)):
    cached = await get_cached_answer(tenant.id, request.question, request.document_id)
    if cached is not None:
        logger.info("query_cache_hit", tenant_id=tenant.id)
        return {**cached, "cached": True}

    logger.info("query_cache_miss", tenant_id=tenant.id)

    chunks = await retrieve_relevant_chunks(request.question, tenant_id=tenant.id, document_id=request.document_id)
    answer = generate_answer(request.question, chunks)
    result = {"answer": answer, "chunks_used": chunks}

    await set_cached_answer(tenant.id, request.question, result, request.document_id)

    return {**result, "cached": False}


@app.get("/documents")
async def list_documents(tenant: Tenant = Depends(get_current_tenant)):
    async with tenant_session(tenant.id) as session:
        documents = (await session.execute(
            select(Document).where(Document.tenant_id == tenant.id).order_by(Document.created_at.desc())
        )).scalars().all()
    return [{"id": doc.id, "filename": doc.filename} for doc in documents]


# Serves the built frontend (frontend/dist) in production so one Docker
# image + one Render service handles both API and UI, no CORS needed.
# Mounted last so it never shadows the API routes above. Skipped locally
# when the frontend hasn't been built (`npm run build`).
if os.path.isdir("frontend/dist"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")
