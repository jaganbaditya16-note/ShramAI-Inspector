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
