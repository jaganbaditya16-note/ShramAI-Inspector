# Architecture Overview

## System shape

```
Browser (Next.js workspace)
   │  same-origin /api/v1 (server proxy in dev/docker, platform rewrite on Vercel)
   ▼
FastAPI (layered monolith)
   ├─ core/        config, structured logging, errors, security, middleware, rate limiting
   ├─ api/v1/      routers: health, auth, cases, documents, findings, reports, audit, dashboard
   ├─ schemas/     pydantic request/response contracts
   ├─ services/    domain logic (validation, storage, extraction, classification,
   │               rules, scoring, retrieval, AI provider, pipeline, reporting, audit)
   ├─ models/      SQLAlchemy 2 ORM (tenanted schema)
   └─ db/          engine/session, Alembic migrations
        │
        ├─ PostgreSQL (production) / SQLite (local demo)
        └─ Document storage (pluggable: local disk for dev / private S3-compatible object store)
```

The deployment unit is deliberately a **layered monolith**: one API service and one
web service. Domain boundaries are enforced in code (service layer + storage
protocol + AI provider protocol) so extraction, rules or AI can be extracted into
separate workers later without touching call-sites.

## Trust boundaries

1. **Browser → API**: session cookie (HttpOnly, SameSite=Lax) or demo principal;
   Origin check on unsafe methods; rate limits; body-size cap.
2. **Upload → storage**: extension + MIME + magic-byte + EOF validation, streaming
   size bound, server-generated storage keys (no client path influence), sha256
   integrity, filename sanitised for display only.
3. **Files → extractors**: bounded page/char/scale limits; parser failures map to
   a safe `extraction_failed` state, never a 500 with internals.
4. **Document text → AI model**: wrapped in explicit untrusted-data delimiters;
   instructions inside documents are never followed; structured JSON output is
   schema-validated; evidence quotes must match the source text (grounding) or the
   finding is rejected.
5. **Findings → report**: report is an immutable snapshot including versions,
   review states, model-run provenance and the score formula.

## Key flows

- **Upload**: `POST /cases/{id}/documents` validates + persists the document and a
  `processing_job`, then returns **202** immediately. The pipeline runs in-process
  (bounded concurrency) and the client polls `GET /documents/{id}`. `PIPELINE_MODE=inline`
  runs the pipeline inside the request for constrained environments.
- **Processing**: extraction (thread pool) → classification → deterministic rules
  (decision-preserving replace) → optional grounded AI analysis (`model_runs` row)
  → case/audit updates. Every terminal state is persisted; startup recovery marks
  jobs interrupted by a restart as failed with a safe message.
- **Review**: `PATCH /findings/{id}` transitions `needs_review ↔ confirmed/dismissed`
  with reviewer + timestamp + optional note, audited.
- **Report**: `POST /cases/{id}/report` snapshots the scorecard (scores, breakdown,
  provenance, disclaimer) into `reports`; regeneration creates a new snapshot.

## Reliability characteristics (verified behaviour)

Guarantees asserted by the automated suites (`test_reliability.py` and friends),
not aspirations:

- **One active job per document.** A partial unique index on
  `processing_jobs(document_id) WHERE status IN ('queued','running')` makes
  duplicate concurrent execution impossible at the storage engine; a reprocess
  racing the check gets `409 conflict`. A reprocess burst never overlaps job
  execution intervals (verified live, 8-way barrier) and the 0004 migration
  supersedes pre-existing duplicate actives on upgrade.
- **Batched list reads.** The documents list fetches latest jobs for the whole
  page in one query (regression-pinned via query counting); case counts were
  already grouped (2 queries per page).
- **Bounded resources.** Upload size caps enforced while streaming; page/char/
  OCR-DPI caps in extraction; AI is a single bounded-timeout attempt with a
  hard input-char limit (no automatic retries, no retry storms); the pipeline
  runs under a semaphore (`pipeline_concurrency`, default 2).
- **Failure containment.** Every pipeline stage persists terminal states with
  safe messages; a document deleted mid-processing fails its job without
  partial rows; storage write failure keeps the DB clean; presign failures
  surface as `503 storage_unavailable` (retryable), not 500s.
- **Recovery.** Startup marks queued/running jobs interrupted by a restart as
  failed with a reprocess hint; the retention sweep is bounded, idempotent and
  error-isolated per stage.
- **Frontend pacing.** Polling is bounded and self-stopping: the documents
  page refetches every 2 s only while something is queued/processing; the
  upload panel polls every 1.2 s with a 120 s deadline and then reports an
  honest timeout.
- **Database posture.** SQLite (development) runs with WAL + enforced foreign
  keys; production should use Postgres (see deployment docs). Rate limiting is
  per-instance; multi-instance deployments enforce limits at the gateway.

## Cross-cutting decisions

| Concern | Approach |
|---|---|
| Tenancy | every table carries `org_id`; all queries filter by it (IDOR-proof by construction) |
| IDs | UUID strings everywhere; human-readable case codes generated separately |
| Auth | cookie sessions, Argon2id passwords, role ranks (`viewer` < `inspector` < `admin`) |
| Errors | `AppError` hierarchy → consistent `{error: {code, message, request_id}}` envelope |
| Logging | JSON logs with request IDs via contextvars; never document text |
| Time | timezone-aware UTC datetimes everywhere (TypeDecorator normalises SQLite) |
| Rules | pure, versioned registry (`RULE_VERSION`), reproducible per text+version |
| AI | provider protocol; Ollama local provider; disabled-by-default, honest status |
| Storage | `DocumentStore` interface: local-disk (dev) and private S3-compatible (production) backends behind `STORAGE_BACKEND`; objects private, keys server-generated and never client-visible |
| Identity | provider-agnostic `IdentityProvider` interface: password (local) and OIDC SSO today; providers only verify identity — sessions, RBAC and tenancy stay local |
| Retention | centralised `retention_service` (config-driven, non-destructive defaults); object-before-row deletion; audit events never deleted; sweeps at startup + admin endpoint (no scheduler) |
