from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from auth import generate_api_key, hash_api_key, get_current_tenant
from db import async_session, tenant_session
from ingestion import process_document
from llm import generate_answer
from models import IngestionJob, JobStatus, Tenant
from retrieval import retrieve_relevant_chunks

app = FastAPI()


class UploadRequest(BaseModel):
    filename: str
    content: str


class QueryRequest(BaseModel):
    question: str


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

    return {"tenant_id": tenant.id, "api_key": raw_key}


@app.post("/documents", status_code=202)
async def upload_document(
    request: UploadRequest,
    background_tasks: BackgroundTasks,
    tenant: Tenant = Depends(get_current_tenant),
):
    async with tenant_session(tenant.id) as session:
        job = IngestionJob(tenant_id=tenant.id, status=JobStatus.pending)
        session.add(job)
        await session.commit()

    background_tasks.add_task(
        process_document, job.id, tenant.id, request.filename, request.content
    )

    return {"job_id": job.id, "status": job.status}


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
async def query_documents(request: QueryRequest, tenant: Tenant = Depends(get_current_tenant)):
    chunks = await retrieve_relevant_chunks(request.question, tenant_id=tenant.id)
    answer = generate_answer(request.question, chunks)
    return {"answer": answer, "chunks_used": chunks}
