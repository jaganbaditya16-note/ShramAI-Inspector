# Security Baseline

## Implemented controls

### Authentication & session
- Argon2id password hashing; uniform login failures (dummy verify on unknown user)
  to prevent account enumeration.
- Opaque session tokens; only SHA-256 hashes stored; expiry + revocation;
  HttpOnly + SameSite=Lax cookies, `Secure` in production.
- Role ranks `viewer < inspector < admin` enforced server-side per endpoint.
- `AUTH_MODE=demo` exists for public synthetic-data demos and is clearly labelled;
  it is never required for production use.

### Authorization & tenancy
- Every table carries `org_id`; every query filters by the principal's org, so
  cross-tenant access is structurally impossible (404, not 403 — no existence leak).
- Soft-deleted cases are excluded from all reads.

### Upload defence
- Extension + declared MIME + magic-byte signature must all agree.
- PDFs must carry an `%%EOF` marker (rejects truncated/parser-abuse probes).
- Streaming read bound (`MAX_UPLOAD_MB`) — oversized bodies are aborted mid-read.
- Filename sanitised for display only; storage keys are server-generated
  (`YYYY/MM/<uuid>.ext`) and validated against a strict shape before any path use.
- sha256 recorded for integrity/dedup analysis.

### Document storage
- Backend-agnostic `DocumentStore` interface; local disk for development/tests,
  private S3-compatible object storage (`STORAGE_BACKEND=s3`) for production.
  Startup refuses `s3` without bucket/credentials and refuses `local` in
  production (fail-fast on demo-grade durability).
- Objects are **private by default**: no ACL is ever granted, no public URLs are
  built. Downloads stream through the authorised API endpoint, which re-checks
  org-scoped access on every request; a redirect to a short-lived presigned GET
  (default TTL 300 s, hard-capped at 1 h) exists only behind
  `S3_PRESIGNED_DOWNLOADS=true`.
- Server-generated, unguessable keys (`YYYY/MM/<uuid>.ext`); every backend
  method validates the key shape first, so client-supplied values can never
  traverse paths on any filesystem or escape the bucket prefix.
- Tenancy: documents are org-scoped in the database; object keys are never
  exposed in API responses, so a tenant cannot address another tenant's object.
- sha256 is computed at validation and stored with the document; downloads are
  byte-exact (integrity verified in tests).
- Storage failures are fail-safe: failed upload writes return
  `503 storage_unavailable` with nothing persisted; failed registrations remove
  their just-written object (no orphans); failed deletes keep the document row
  (no dangling record); missing objects return a safe 404.
- Credentials live only in environment configuration; they never appear in
  logs, errors, health output, `repr`, or the frontend.

### Malware scanning
- Optional pre-processing stage (`MALWARE_SCAN_MODE=off|enforcing`, default
  `off` for local/demo development) in front of every upload:
  validate → **scan** → store → register. Scanning happens before any bytes are
  written to storage or any rows are committed.
- Clean-scan interface (`MalwareScanner` ABC) with a ClamAV clamd INSTREAM
  adapter; nothing else in the codebase knows about clamd specifics.
- `off` mode never claims a clean result — documents get `scan_status=skipped`
  and an audit event; startup refuses to boot in production with scanning off.
- `enforcing` mode is **fail-closed**: an unreachable, timed-out, or erroring
  scanner blocks the upload (`503` / `413`), nothing is persisted, and an audit
  event records the verdict — an unavailable scanner is never treated as clean.
- Signature match → upload rejected (`400 infected_document`), document marked
  `rejected` with the signature name and sha256 retained for incident response,
  stored bytes and any pipeline processing withheld.
- Defence in depth: the pipeline itself refuses any document whose
  `scan_status` is not `clean`/`skipped`, and reprocessing is refused (`409`).
- Only verdict metadata is persisted/logged (engine, verdict, signature name
  capped at 160 chars, duration); file contents and raw scanner replies never
  enter logs, audit events, or API responses. Streamed to clamd in bounded
  64 KiB chunks so scan memory does not scale with file size; existing upload
  and request body limits are unchanged and still apply first.

### HTTP surface
- Security headers: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`,
  `Permissions-Policy`, `Cache-Control: no-store`, HSTS outside local SQLite.
- Request-body size cap; per-IP sliding-window rate limits (default / auth /
  upload buckets); `429` + `Retry-After`.
- Origin check on unsafe methods (CSRF defence for cookie sessions).
- CORS is an explicit allow-list; empty default = same-origin only.
- Consistent error envelope; stack traces never leave the server (logged with
  request IDs instead).

### AI safety
- Document text is untrusted data: delimited in prompts, never executed as
  instructions.
- Strict Pydantic schema on model output (extra fields forbidden).
- Evidence grounding: AI findings whose quotes cannot be located verbatim in the
  extracted text are rejected and counted on `model_runs`.
- AI findings are always created as `needs_review`; no code path auto-confirms.

### Audit
- Append-only `audit_events` with actor, action, request ID and id-only details —
  never document text.

## Required from deployment infrastructure (not code)

- TLS termination with HSTS already sent; approved identity provider (SSO) for
  government use.
- Durable PostgreSQL + private object storage with encryption/KMS; the storage
  protocol exists for this swap.
- Malware scanning/quarantine before OCR (clamd or platform service).
- Centralised secrets management; centralised log aggregation + alerting;
  multi-instance rate limiting (Redis/gateway).
- Backups + restore testing; configurable retention/deletion jobs (schema supports
  hard-delete of documents incl. stored files).
- Formal DPDP/privacy review before real worker data.
