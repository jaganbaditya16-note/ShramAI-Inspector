# Data lifecycle: retention & deletion

This document defines what persistent data exists, when it expires, how
deletion works, and what is preserved on purpose.

## 1. Persistent data inventory

| Data | Where | Notes |
|---|---|---|
| Document originals | object storage (`DocumentStore`: local disk or private S3-compatible bucket) | one object per document; server-generated keys |
| Extracted text + page map | `documents.extracted_text`, `documents.page_map` | lives inside the document row — no separate text store |
| Findings + evidence (quotes, hashes, offsets) | `findings` | cascade with the document/case |
| AI model runs (metadata + counts only, no prompts) | `model_runs` | cascade with the document |
| Processing jobs | `processing_jobs` | cascade with the document; never resurrect deleted data |
| Reports | `reports` (case-level JSON) | cascade with the case |
| Audit events | `audit_events` | **no FK by design** — survive every purge; ids + categories only, never document contents |
| Auth sessions | `auth_sessions` | expired rows are cleaned by retention; users untouched |
| Cases | `cases` (`deleted_at` = soft delete) | active cases are never deleted by retention |
| Document versions | — | the system stores a single current version per document (no version table) |

## 2. Retention policy (environment-configurable, non-destructive defaults)

| Setting | Default | Meaning |
|---|---|---|
| `RETENTION_DOCUMENT_DAYS` | `0` (never) | purge a document N days after upload |
| `RETENTION_REJECTED_DOCUMENT_DAYS` | `7` | rejected/failed documents carry no review value; shorter window (0 = keep) |
| `RETENTION_CASE_DAYS` | `0` (never) | **soft-deleted** cases are hard-purged N days after soft-deletion |
| `RETENTION_SESSION_DAYS` | `30` | expired session rows removed N days after expiry |
| `RETENTION_PURGE_BATCH` | `100` | upper bound of work per sweep (predictable runtime) |

- **Case retention vs audit retention are distinct**: purging a case removes
  its documents/findings/reports/storage objects; its audit events remain as
  required evidence. There is currently no audit expiry — if an operator sets
  one it must satisfy the applicable legal minimum (DPDP/intent records); the
  schema supports it, the policy deliberately does not enable it.
- **Active cases are never deleted** — only explicitly soft-deleted cases
  (user action in the UI/API) become hard-purge candidates.

## 3. Deletion mechanics (`app/services/retention_service.py`)

All destructive logic lives in the retention service (routers and startup
delegate to it):

1. **Documents**: storage object deleted **first**, then the row (with its
   extracted text, findings, model runs and jobs via cascade). If the storage
   backend fails, the row is **kept** — the row is the ledger that makes the
   deletion retryable; deleting it first would orphan the object. A missing
   object counts as success (idempotent). Every purge appends a
   `retention_document_purged` audit event (ids + sha256 prefix only).
2. **Cases** (hard purge): every document object is removed first; only when
   none are pending is the case row deleted (cascading everything). Partial
   storage failures defer the whole case to the next sweep and raise a
   `retention_purge_failed` audit event.
3. **Sessions**: expired `auth_sessions` rows past the retention window are
   removed; users and audit are untouched.

### Safety properties

- **Idempotent**: sweeps can run any number of times; repeated deletes are
  no-ops (already-purged documents 404 consistently).
- **Race safety**: documents with `queued`/`running` processing jobs are
  excluded from sweeps; the pipeline re-fetches rows and fails safely when a
  document vanished (an expired job can never revive deleted data).
- **Tenant safety**: sweeps are instance-level operator functions (admin role
  only). User-initiated deletion (`DELETE /api/v1/documents/{id}`) is
  org-scoped via the standard authorisation path — cross-tenant deletion
  attempts are indistinguishable 404s.
- **Signed URLs**: presigned downloads are opt-in and capped at 1 hour; the
  underlying object is deleted at purge time, so any previously-minted URL is
  dead on arrival (the provider 404s it). The default API download path
  re-checks authorisation per request and returns 404 after deletion.
- **Audit contents**: purge events carry ids, verdict categories and sha256
  prefixes — never document text, quotes or storage keys.

## 4. How sweeps run (deliberately simple)

- **Startup**: one bounded sweep runs in the API lifespan (existing
  architecture; no new scheduler/queue process).
- **On demand**: `POST /api/v1/admin/retention/run` (admin role) for
  cron/CI-invoked periodic sweeps.

No scheduler, queue or background worker was introduced for this — the
simplest reliable mechanism is a cheap, bounded, idempotent function that the
platform already-running components call.
