"""
Ingest the eval PDFs through doc-query's REAL pipeline (ingestion.process_document),
so the eval measures your actual production path: same dedup hash, chunking,
embedding, and storage as a live upload.

Run from your project root (so `db`, `models`, `ingestion` import) after putting
the 10 PDFs in ./data:

    pip install pypdf
    python ingest_eval_pdfs.py

Requirements:
  - TENANT_ID is an EXISTING tenant. Use a dedicated eval tenant if you can, so
    eval data doesn't mix with real tenants' documents.
  - Your app's services (DB, and whatever invalidate_tenant_cache needs) are up,
    since we're calling the real pipeline.
  - Page extraction below uses pypdf. If your upload handler extracts pages a
    different way (pdfplumber / PyMuPDF / OCR), import and use THAT function so
    page boundaries match production — just swap extract_pages().
"""

import asyncio
import uuid
from pathlib import Path

from db import tenant_session
from logging_config import configure_logging
from models import IngestionJob, JobStatus
from ingestion import process_document
from pdf_extraction import extract_pages_from_pdf

TENANT_ID = 2
DATA_DIR = Path("data")


def extract_pages(path: Path) -> list[str]:
    """One string per PDF page, using the same extractor production uploads use."""
    return extract_pages_from_pdf(path.read_bytes())


async def ingest_one(path: Path, tenant_id: int) -> None:
    pages = extract_pages(path)
    if not any(p.strip() for p in pages):
        # Fully scanned PDF -> your chunker drops empty text -> 0 chunks ->
        # the doc is never retrievable. Flag it instead of silently ingesting.
        print(f"  warn  {path.name}: no extractable text (scanned PDF?) — skipping")
        return

    # process_document expects an existing IngestionJob; create one first.
    async with tenant_session(tenant_id) as session:
        job = IngestionJob(tenant_id=tenant_id, status=JobStatus.pending)
        session.add(job)
        await session.flush()          # populate job.id
        job_id = job.id
        await session.commit()

    # Drive the real pipeline (handles dedup, chunking, embedding, storage).
    await process_document(
        job_id=job_id,
        tenant_id=tenant_id,
        filename=path.name,
        pages=pages,
        request_id=f"eval-{uuid.uuid4().hex[:8]}",
    )

    # process_document swallows errors into job.status, so read the outcome back.
    async with tenant_session(tenant_id) as session:
        job = await session.get(IngestionJob, job_id)
        if job and job.status == JobStatus.done:
            print(f"  ok    {path.name}: job {job_id} -> done (document_id={job.document_id})")
        else:
            status = job.status.value if job else "missing"
            err = f" - {job.error_message}" if (job and job.error_message) else ""
            print(f"  FAIL  {path.name}: job {job_id} -> {status}{err}")


async def main() -> None:
    configure_logging()
    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs in {DATA_DIR.resolve()}")
    print(f"Ingesting {len(pdfs)} PDFs into tenant {TENANT_ID} via process_document...")
    for path in pdfs:
        await ingest_one(path, TENANT_ID)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())