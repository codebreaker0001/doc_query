# Doc-Query — How It Works, What's Broken, What's Missing for Production

## 1. What this project is

A multi-tenant RAG (Retrieval-Augmented Generation) backend: a tenant uploads a PDF,
the system extracts/chunks/embeds it, and the tenant can then ask natural-language
questions that get answered using only the content of their own documents.

**Stack:** FastAPI (API) · PostgreSQL + pgvector (Neon) · Redis (Upstash) · RQ (job queue)
· sentence-transformers (embeddings + reranking, local CPU models) · Groq (LLM answer
generation) · React/Vite (frontend).

## 2. Request flow, end to end

### 2a. Tenant signup
`POST /tenants` ([main.py:101-112](main.py#L101-L112)) creates a row in `tenants`, generates a random
API key (`secrets.token_hex(32)`), stores only its SHA-256 hash
([auth.py:15-20](auth.py#L15-L20)), and returns the raw key to the caller **once**. Every
subsequent request authenticates via the `X-API-Key` header
([auth.py:23-34](auth.py#L23-L34)), which is hashed and looked up — nothing else proves
identity, there's no session/JWT.

### 2b. Document upload → async ingestion
`POST /documents` ([main.py:115-147](main.py#L115-L147)):
1. Checks `Content-Type` is `application/pdf` and `Content-Length` is under 20MB.
2. Reads the whole file into memory, extracts text per page
   ([pdf_extraction.py](pdf_extraction.py)) — falls back to Tesseract OCR on pages with
   no extractable text (scanned PDFs).
3. Rejects the upload if literally nothing is extractable.
4. Creates an `ingestion_jobs` row (`status=pending`) and **enqueues** the actual work
   on an RQ/Redis queue — the HTTP response returns immediately with a `job_id`
   (202 Accepted). The frontend polls `GET /jobs/{job_id}` every 1.5s
   ([App.jsx:87-107](frontend/src/App.jsx#L87-L107)) until it flips to `done`/`failed`.

The queued job ([ingestion.py](ingestion.py)) runs in a worker process/thread:
- Hashes the full document text (SHA-256) and skips re-processing if a document with
  the same hash already exists for that tenant (dedup on re-upload).
- Splits text into ~500-token chunks with 2-sentence overlap
  ([chunking.py](chunking.py)), using `tiktoken` for token counting and a regex
  sentence splitter.
- Embeds every chunk with `BAAI/bge-small-en-v1.5` (384-dim vectors,
  [embed.py](embed.py)).
- Writes `Document` + `Chunk` rows (chunk content + embedding vector) in one
  transaction, marks the job `done`, and invalidates that tenant's query cache.

**Where the worker actually runs** is the trickiest part of this codebase
([main.py:44-62](main.py#L44-L62)): Render's free tier gives one process and 512MB RAM,
too little for a second copy of torch/transformers in a separate worker process. So in
production the "worker" is a **daemon thread inside the same FastAPI process**
(`ENABLE_EMBEDDED_WORKER=true`), sharing the one loaded model. Locally/on a real
multi-process host, [worker.py](worker.py) can run as a standalone RQ worker instead.

### 2c. Querying
`POST /query` ([main.py:165-180](main.py#L165-L180)):
1. Checks Redis for a cached answer, keyed by `tenant_id + question hash +
   document_id` ([cache.py](cache.py)), 1-hour TTL. Cache hit → return immediately.
2. On a miss: embeds the question, pulls the 15 nearest chunks by cosine distance from
   pgvector (scoped to the tenant, optionally to one document,
   [retrieval.py](retrieval.py)), then **reranks** those 15 with a cross-encoder
   (`ms-marco-MiniLM-L-6-v2`) down to the top 3 — a two-stage retrieve-then-rerank
   pipeline, which is why quality is decent despite a cheap vector search.
3. Stuffs the 3 chunks into a prompt and asks Groq (`openai/gpt-oss-20b`) to answer
   only from that context ([llm.py](llm.py)).
4. Caches and returns `{answer, chunks_used, cached}`.

### 2d. Multi-tenancy
Every table that holds tenant data has a `tenant_id` column, and every query filters
on it explicitly (`.where(Document.tenant_id == tenant_id)` in
[retrieval.py](retrieval.py#L18), [ingestion.py](ingestion.py#L33), etc.) — this is
**application-level** tenant isolation, done by discipline in each query, not enforced
by the database. (See Bug #2 in §3: this used to be masked by a dead `SET LOCAL` call
that looked like DB-level isolation but wasn't — now removed.)

### 2e. Everything else
- **Rate limiting**: 4 requests/60s per tenant, fixed-window counter in Redis
  ([rate_limit.py](rate_limit.py)).
- **Logging**: structured JSON logs via `structlog`, one `request_id` bound per HTTP
  request ([logging_config.py](logging_config.py), [main.py:75-86](main.py#L75-L86)).
- **Deployment**: single Docker image builds the React frontend, then copies
  `frontend/dist` into the Python image; FastAPI serves the API at `/*` routes and the
  built frontend as static files at `/` ([Dockerfile](Dockerfile),
  [main.py:192-197](main.py#L192-L197)). One Render web service
  ([render.yaml](render.yaml)), no separate frontend hosting, no CORS to configure in
  that deployment.
- **Evals**: `evals/` has two harnesses against the same golden dataset
  ([evals/golden_dataset.py](evals/golden_dataset.py)) and eval tenant (id `2`, all 14
  arXiv PDFs in `data/` already ingested):
  - `eval_retrieval.py` — DeepEval's contextual precision/recall/relevancy, grading
    **retrieval only** (judged by a Groq model via a hand-written `DeepEvalBaseLLM`
    wrapper, [evals/groq_judge.py](evals/groq_judge.py)).
  - `eval_ragas.py` — RAGAS's faithfulness, answer relevancy, context precision, and
    context recall. This one also grades the **generated answer**
    (faithfulness/relevancy), which `eval_retrieval.py` doesn't — it catches "retrieval
    was fine but the LLM hallucinated anyway," a failure mode the DeepEval harness is
    blind to. Judge: Groq via `ragas`'s `LangchainLLMWrapper`; embeddings: the same
    local `BAAI/bge-small-en-v1.5` model production uses, via `LangchainEmbeddingsWrapper`.
    One caveat baked into the code: RAGAS's answer-relevancy metric samples 3
    completions per answer for self-consistency by default (`strictness=3`, i.e. an
    LLM call with `n=3`) — Groq's API flatly rejects `n>1`, so `eval_ragas.py` sets
    `strictness=1`. One side effect worth knowing: `ragas` pulls in `langchain-groq`,
    which pins `groq<1.0.0` — incompatible with the `groq==1.5.0` this project pinned
    before. `requirements.txt` now pins `groq==0.37.1` instead; its chat-completions
    API (used by [llm.py](llm.py) and [groq_judge.py](evals/groq_judge.py)) is
    unchanged across that range, verified by running both after the downgrade.

## 3. Bugs found while reading the code (all fixed below)

### Bug 1 — `NameError` on every clean shutdown — FIXED
[main.py:61-62](main.py#L61-L62) called `worker_process.terminate()` on a name that was
never defined anywhere in the file (only the embedded-worker `thread` existed). The
`lifespan` context manager raised `NameError` on every app shutdown — graceful
shutdown always crashed, logs got noisy, and container orchestrators checking exit
codes would see a failure on every restart/deploy.
**Fix applied:** deleted those two lines. The embedded worker is a daemon thread; it
dies with the process, there was never anything to terminate.

### Bug 2 — Tenant isolation looked DB-enforced but wasn't; raw SQL interpolation — FIXED
[db.py](db.py) used to run:
```python
async def tenant_session(tenant_id: int):
    async with async_session() as session:
        await session.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))
        yield session
```
This sets a Postgres session variable that only matters if a Row-Level-Security
`POLICY` reads `current_setting('app.tenant_id')` — grepping the whole repo, **no such
policy, and no `ENABLE ROW LEVEL SECURITY`, existed anywhere**. The line did nothing;
the real tenant boundary was (and still is) the manual `.where(tenant_id == ...)` on
each query. It also built SQL via an f-string — not exploitable since `tenant_id` is
always an authenticated `int`, but a SQL-injection-shaped pattern sitting in shared
code is a bad habit to leave around.
**Fix applied:** removed the dead `SET LOCAL` call; `tenant_session` is now a plain
session context manager. The `tenant_id` parameter is kept unused on purpose, so every
call site still reads as "this session is scoped to a tenant" — the actual enforcement
remains the explicit query filters, now without a line implying otherwise. Real
DB-level enforcement (actual RLS policies) is still worth adding — see §4 item 1.

### Bug 3 — Upload size cap could be bypassed; whole file buffered in memory — FIXED
[main.py](main.py) used to check `Content-Length` — a client-supplied header, absent
under chunked transfer-encoding or simply spoofable — then call `await file.read()`
unbounded. A missing/false header meant an unbounded upload got buffered straight into
the same 512MB-constrained process that also holds the embedding model: a cheap
memory-exhaustion vector.
**Fix applied:** added `_read_upload_capped()` ([main.py](main.py)), which reads the
upload in 1MB chunks and raises `413` the moment the running total passes
`MAX_UPLOAD_BYTES` — the cap is now enforced by what's actually read, not by a header
that can be omitted or lied about. The `Content-Length` pre-check is kept too, as a
cheap fast-reject before any bytes are read.

### Bug 4 — Content-type check was trivially spoofable — FIXED
[main.py](main.py) only checked the client-supplied `file.content_type` string, not the
actual bytes. A non-PDF with `Content-Type: application/pdf` set manually used to fail
downstream in `PdfReader` with an unhandled exception (a raw 500, not a clean 400).
**Fix applied:** after the capped read, the handler now also checks the magic bytes
(`file_bytes.startswith(b"%PDF")`) and returns a clean `400` if they don't match — the
same check already used correctly in [download.py:59](download.py#L59).

### Bug 5 — Blocking calls inside async request handlers — FIXED
`embed_texts`/`rerank` (sentence-transformers, CPU-bound) and `generate_answer` (Groq's
synchronous HTTP client) used to be called directly from `async def` route handlers —
[retrieval.py](retrieval.py) and [main.py](main.py). FastAPI's event loop is
single-threaded for async code; a blocking call inside an `async def` function freezes
that loop for every other request until it returns. Under any real concurrency, every
other request — including unrelated tenants' uploads or queries — queued up behind
whichever query was currently embedding or waiting on Groq.
**Fix applied:** both call sites now run the blocking work off the event loop via
`asyncio.to_thread(...)` — `retrieve_relevant_chunks` for `embed_texts`/`rerank`
([retrieval.py](retrieval.py)), and the `/query` handler for `generate_answer`
([main.py](main.py)).

## 4. What's missing to call this "production grade"

Roughly in priority order:

1. **Add real DB-level tenant isolation (RLS policies).** §3 Bug 2's fix removed the
   dead, misleading `SET LOCAL` call; isolation today is 100% "every query remembers
   its `WHERE tenant_id=`". For real defense-in-depth, add actual Postgres RLS
   policies keyed off a session variable, or at minimum a test that fails if any
   tenant-scoped table is queried without a `tenant_id` filter.
2. **Schema migrations.** [init_db.py](init_db.py) does `drop_all` + `create_all` —
   fine for a demo, destroys all data on every schema change. Add Alembic before this
   touches real user data.
3. **Health/readiness endpoint** for the load balancer/orchestrator to poll — there is
   currently no `/health`.
4. **Timeouts and retries on the Groq call.** A hung or 5xx-ing Groq request currently
   has no explicit timeout/retry and no try/except — it surfaces as a raw 500 to the
   user instead of a clean "try again" error.
5. **Real worker/process separation at scale.** The embedded-thread worker is a
   deliberate, documented tradeoff for Render's free tier
   ([main.py:46-52](main.py#L46-L52)) — fine for a portfolio demo, but it means one
   slow ingestion job can starve the same process serving queries. On a real
   deployment, run `worker.py` as its own process/service and drop
   `ENABLE_EMBEDDED_WORKER`.
6. **Abuse controls on `/tenants`.** Anyone can mint unlimited tenants/API keys with no
   verification, each one able to burn your Groq budget via `/query`. Needs at least an
   IP-based rate limit, ideally email verification or an invite step before going
   public.
7. **Observability beyond stdout JSON logs.** No metrics (request latency, queue
   depth, cache hit rate), no error tracking (Sentry or similar), no tracing. You'd be
   flying blind on a production incident today.
8. **CI.** No `.github/workflows` — no automated test/lint run on push. At minimum,
   wire up the existing `evals/` retrieval-quality check and a lint pass.
9. **Secrets management.** `.env` files are fine for a solo project; a real deploy
   should pull `GROQ_API_KEY`/`DATABASE_URL` from the platform's secret store (Render
   already does this via `sync: false` env vars — just don't let a `.env` with real
   keys end up in the image or git history).
10. **Pagination on `/documents`** and any other list endpoint, before a tenant with
    hundreds of documents makes that response huge.
11. **Declare the API-key header as a FastAPI security scheme** (`APIKeyHeader`) so
    `/docs` gets a working "Authorize" button — purely a DX nicety, not a bug.
