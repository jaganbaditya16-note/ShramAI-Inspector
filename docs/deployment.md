# Deployment

## Environments

| Environment | Database | Storage | Auth | Notes |
|---|---|---|---|---|
| `local` | SQLite (auto-create) | local disk | demo | developer laptops |
| `development` / `demo` | SQLite or Postgres | local disk | demo | docker compose, public demos |
| `staging` | managed PostgreSQL | object storage | required | production-like validation |
| `production` | managed PostgreSQL | durable private object storage | required (+SSO) | real data only after security review |

## Supported topologies

### Docker Compose (reference)
`docker compose up --build` — Postgres 17 + API (migrations run at start) +
Next.js web. The web container proxies same-origin `/api/v1` to the API container
(build-time `API_ORIGIN=http://api:8000`); document bytes live in a named volume.

### Vercel Services (single domain)
Root `vercel.json` routes `/api/*` to the containerised API
(`apps/api/Dockerfile.vercel`) and everything else to the Next.js web project.
The Vercel container filesystem is **ephemeral**: SQLite under `/tmp` and local
storage are demo-only. Before real use, set managed `DATABASE_URL` and durable
storage (the `DocumentStore` protocol is the swap point).

### Any container host
`apps/api/Dockerfile` (runs Alembic then uvicorn) + `apps/web/Dockerfile`
(`API_ORIGIN` build arg). No local filesystem persistence is required by design —
point `STORAGE_DIR` at a mounted durable volume until object storage is wired.

## Production checklist (all required before real data)

1. `APP_ENV=production`, `AUTH_MODE=required`
2. `BOOTSTRAP_ADMIN_EMAIL` + `BOOTSTRAP_ADMIN_PASSWORD` set (startup refuses
   otherwise); change the password after first login
3. `DATABASE_URL` → managed PostgreSQL with backups + PITR
4. `STORAGE_BACKEND=s3` with a **private** bucket (startup refuses local disk in
   production): encryption at rest (`S3_SERVER_SIDE_ENCRYPTION`, e.g. `AES256`
   or `aws:kms`), bucket public access blocked, no public URLs — downloads are
   streamed through the authorised endpoint; presigned redirects only if you
   explicitly set `S3_PRESIGNED_DOWNLOADS=true` (short-lived by default)
5. TLS termination; `TRUST_PROXY_HEADERS=true` behind the proxy
6. `MALWARE_SCAN_MODE=enforcing` with a reachable clamd host (startup refuses
   scanning-off in production)
7. Centralised secrets (never `.env` files on hosts)
8. Centralised log aggregation + alerting on `internal_error` / `processing_failed`
9. Multi-instance rate limiting at the gateway (the in-app limiter is per-instance)
10. Retention/deletion policy implemented as scheduled jobs (schema supports
    hard delete incl. stored files); backup-restore tested
11. Security/privacy review (DPDP alignment) and approved integration agreements

## Document storage backends

| Backend | Setting | Use |
|---|---|---|
| Local disk (default) | `STORAGE_BACKEND=local`, `STORAGE_DIR` | development/tests only; startup refuses it in production |
| S3-compatible object store | `STORAGE_BACKEND=s3` | production: AWS S3, MinIO, Cloudflare R2, ... |

Required for `s3`: `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`
(startup refuses otherwise). Optional: `S3_ENDPOINT_URL` (non-AWS endpoints),
`S3_REGION`, `S3_SESSION_TOKEN`, `S3_SERVER_SIDE_ENCRYPTION`. Credentials are
read from the environment only — never hard-coded, never logged, never exposed
to the frontend. Objects are private by default (no ACL is ever granted);
storage failures map to safe `503 storage_unavailable` responses and failed
registrations clean up their object (no orphans). See
`docs/security/security.md` for the control detail and ADR-008 for the decision.

## Configuration reference

See `.env.example` for every variable with documented defaults. All configuration
is environment-driven; no secrets exist in source.
