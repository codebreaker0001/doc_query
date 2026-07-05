import hashlib

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import select

from chunking import split_into_chunks
from db import async_session
from embed import embed_texts
from models import Chunk, Document

app = FastAPI()


class UploadRequest(BaseModel):
    filename: str
    content: str


@app.post("/documents")
async def upload_document(request: UploadRequest):
    content_hash = hashlib.sha256(request.content.encode()).hexdigest()

    async with async_session() as session:
        existing = await session.scalar(
            select(Document).where(Document.content_hash == content_hash)
        )
        if existing is not None:
            return {"document_id": existing.id, "message": "document already uploaded"}

        chunks_text = split_into_chunks(request.content)
        embeddings = embed_texts(chunks_text)

        document = Document(filename=request.filename, content_hash=content_hash)
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
