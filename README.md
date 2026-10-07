# repo-qa-service

Multi-tenant RAG backend: upload PDFs, ask questions, get answers grounded in your documents.

**Live demo:** <!-- TODO: paste deploy URL -->

## Stack

FastAPI · Postgres/pgvector (Neon) · Redis (Upstash) · Groq (LLM) · sentence-transformers (embeddings + reranking) · React/Vite frontend

## Prerequisites

- Python 3.11+
- Node 18+
- Postgres with the `pgvector` extension (e.g. a free [Neon](https://neon.tech) project)
- Redis (e.g. a free [Upstash](https://upstash.com) database)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed and on your `PATH` (only needed for scanned/image PDFs — falls back to OCR when a page has no extractable text)

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # or `source venv/bin/activate` on Mac/Linux
pip install -r requirements.txt
```

Create `.env` in the project root:

```
DATABASE_URL=postgresql://...
GROQ_API_KEY=...
REDIS_URL=...
```

Create the tables:

```bash
python init_db.py
```

Run the backend:

```bash
uvicorn main:app --reload
```

Run the frontend (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

Frontend expects the API at `http://localhost:8000`, and the API's CORS is set for `http://localhost:5173` — both are the defaults, no config needed for local dev.

## Usage

1. Open the frontend, create a tenant (or paste an existing API key) to get an API key.
2. Upload a PDF.
3. Ask questions about it.

## Evals

`evals/` has a DeepEval-based retrieval quality harness (Contextual Precision/Recall/Relevancy, judged via Groq). See `evals/eval_retrieval.py` for usage; results are saved to `evals/results.json`.
