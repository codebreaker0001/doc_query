# Doc-Query

A multi-tenant RAG (Retrieval-Augmented Generation) backend. A tenant uploads a PDF,
the service extracts, chunks, and embeds it, and the tenant can then ask
natural-language questions answered only from the content of their own documents.

**Stack:** FastAPI · PostgreSQL + pgvector (Neon) · Redis (Upstash) · RQ (job queue) ·
sentence-transformers (embeddings + reranking) · Groq (LLM answer generation) ·
React/Vite (frontend).

> For a line-by-line walkthrough of the request flow, known bugs found/fixed, and a
> production-readiness checklist, see [explanation.md](explanation.md).

## Features

- **Multi-tenant** — each tenant gets an API key; every document and query is scoped
  to that tenant.
- **Async ingestion** — upload returns immediately with a `job_id`; a background
  worker extracts text (with OCR fallback for scanned PDFs), chunks it, embeds it, and
  writes it to the database. The frontend polls job status until it's done.
- **Retrieve-then-rerank querying** — pgvector cosine search pulls the top 15 chunks,
  a cross-encoder reranks them down to the top 3, and Groq answers from that context
  only.
- **Caching & rate limiting** — Redis-backed answer cache per tenant/question/document,
  and a per-tenant request rate limit.
- **Dedup on re-upload** — documents are hashed; re-uploading the same file for the
  same tenant is a no-op.
- **Evals** — two harnesses (DeepEval and RAGAS) grade retrieval and generation quality
  against a golden dataset.

## Architecture

```
            ┌──────────┐      upload PDF       ┌─────────────┐
 tenant ───▶│ FastAPI  │──────────────────────▶│  RQ queue   │
            │  API     │                        │ (Redis)     │
            └────┬─────┘                        └──────┬──────┘
                 │  ask question                        │
                 ▼                                       ▼
          ┌─────────────┐                        ┌──────────────┐
          │  pgvector    │◀──embed + store───────│ ingestion    │
          │  (Postgres)  │                        │ worker       │
          └──────┬───────┘                        └──────────────┘
                 │ top-k chunks → rerank → top-3
                 ▼
          ┌─────────────┐
          │   Groq LLM   │──▶ answer
          └─────────────┘
```

## API

| Method | Path              | Auth        | Description                          |
|--------|-------------------|-------------|--------------------------------------|
| POST   | `/tenants`         | —           | Create a tenant, returns an API key  |
| POST   | `/documents`       | API key     | Upload a PDF, returns a `job_id`     |
| GET    | `/jobs/{job_id}`   | API key     | Poll ingestion job status            |
| GET    | `/documents`       | API key     | List the tenant's documents          |
| POST   | `/query`           | API key     | Ask a question, get an answer        |

Authenticate with an `X-API-Key` header set to the key returned by `/tenants`.

## Running locally

**Requirements:** Python 3.11+, Node 18+, a PostgreSQL database with the `pgvector`
extension, a Redis instance, and a [Groq](https://console.groq.com) API key.

```bash
# Backend
pip install -r requirements.txt
cp .env.example .env   # fill in DATABASE_URL, GROQ_API_KEY, REDIS_URL
python init_db.py
uvicorn main:app --reload

# Worker (separate process, unless ENABLE_EMBEDDED_WORKER=true)
python worker.py

# Frontend
cd frontend
npm install
npm run dev
```

Environment variables (`.env`):

| Variable                | Purpose                                              |
|--------------------------|-------------------------------------------------------|
| `DATABASE_URL`           | Postgres connection string (pgvector extension)       |
| `GROQ_API_KEY`           | LLM answer generation                                 |
| `REDIS_URL`               | Job queue + answer cache + rate limiting              |
| `TESSERACT_CMD`           | Path to the Tesseract binary (OCR fallback)           |
| `ENABLE_EMBEDDED_WORKER` | `true` to run the RQ worker as a thread in the API process (used in the single-process deployment) |
| `CORS_ORIGINS`            | Comma-separated allowed origins (default `http://localhost:5173`) |

## Evals

```bash
python evals/eval_retrieval.py   # DeepEval: retrieval quality
python evals/eval_ragas.py       # RAGAS: retrieval + generation quality
```

Both run against a golden dataset of arXiv PDFs already ingested for a fixed eval
tenant. See [explanation.md](explanation.md#2e-everything-else) for how each is scored.

## Deployment

A single Docker image builds the React frontend and serves it as static files from
the same FastAPI process that serves the API — one Render web service, no separate
frontend host, no CORS to configure in that setup. See [Dockerfile](Dockerfile) and
[render.yaml](render.yaml).

## Known limitations

Tenant isolation is enforced by an explicit `WHERE tenant_id = ...` on every query, not
by database-level row security; there's no schema migration tool (`init_db.py` recreates
tables from scratch); and the "worker" is a background thread sharing the API process's
memory rather than a separate service, to fit a 512MB free-tier host. These and other
gaps are listed with context in [explanation.md §4](explanation.md#4-whats-missing-to-call-this-production-grade).
