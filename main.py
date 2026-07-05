import hashlib

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import select

from chunking import split_into_chunks
from db import  tenant_session
from embed import embed_texts
from models import Chunk, Document
from llm import generate_answer
from retrieval import retrieve_relevant_chunks
from auth import generate_api_key, hash_api_key
from models import Tenant
from fastapi import Depends, FastAPI
from auth import generate_api_key, hash_api_key, get_current_tenant
from models import Chunk, Document, Tenant


app = FastAPI()

class TenantSignupRequest(BaseModel):
    name: str


@app.post("/tenants")
async def create_tenant(request: TenantSignupRequest):
    raw_key = generate_api_key()
    api_key_hash = hash_api_key(raw_key)

    async with tenant_session(tenant_id) as session:
        tenant = Tenant(name=request.name, api_key_hash=api_key_hash)
        session.add(tenant)
        await session.commit()

    return {"tenant_id": tenant.id, "api_key": raw_key}




class UploadRequest(BaseModel):
    filename: str
    content: str



class QueryRequest(BaseModel):
    question: str


@app.post("/query")
async def query_documents(request: QueryRequest, tenant: Tenant = Depends(get_current_tenant)):
    chunks = await retrieve_relevant_chunks(request.question, tenant_id=tenant.id)
    answer = generate_answer(request.question, chunks)
    return {"answer": answer, "chunks_used": chunks}



@app.post("/documents")
async def upload_document(request: UploadRequest, tenant: Tenant = Depends(get_current_tenant)):
    content_hash = hashlib.sha256(request.content.encode()).hexdigest()

    async with tenant_session(tenant.id) as session:
        existing = await session.scalar(
            select(Document).where(
                Document.content_hash == content_hash,
                Document.tenant_id == tenant.id,
            )
        )
        if existing is not None:
            return {"document_id": existing.id, "message": "document already uploaded"}

        chunks_text = split_into_chunks(request.content)
        embeddings = embed_texts(chunks_text)

        document = Document(tenant_id=tenant.id, filename=request.filename, content_hash=content_hash)
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

        await session.commit()

    return {"document_id": document.id, "num_chunks": len(chunks_text)}
