# ShramAI Inspector

AI-assisted labour-document inspection platform: turn uploaded labour documents into
**evidence-linked screening signals** for authorised human review.

Built for Digital Shram Sankalp — Problem Statement #5: *AI-Driven Smart Inspection
System for Labour Code Compliance (Shram Suvidha Portal)*.

## What it does

```
UPLOAD → VALIDATE → STORE → EXTRACT (text/OCR) → CLASSIFY → RULE ENGINE
       → OPTIONAL AI ANALYSIS (grounded) → FINDINGS → HUMAN REVIEW
       → AUDIT TRAIL → SCREENING SCORECARD
```

- **Deterministic first**: versioned, tested screening rules handle hard checks.
- **AI is assistive and grounded**: the optional local-model analysis must cite
  verbatim document evidence; ungrounded quotes are rejected automatically.
- **Humans decide**: every substantive finding requires explicit review
  (confirm / dismiss) that is audited and stamped with reviewer + time.
- **Never a legal authority**: no invented laws, citations, penalties or
  deadlines — wording and workflow enforce this.

## Monorepo layout

```
apps/
  web/    Next.js 16 inspector workspace (App Router, TypeScript, TanStack Query,
          Framer Motion, accessible design system)
  api/    FastAPI backend (layered: core / api / schemas / services / models),
          SQLAlchemy 2 + Alembic, PostgreSQL or SQLite
data/
  demo/        synthetic demo guidance
  knowledge/   approved, versioned reference corpus (markdown, provenance headers)
docs/
  architecture/  system, data model, API contract, pipeline, frontend
  security/      security baseline and threat model
  compliance/    AI governance
  deployment.md  environments and production requirements
  development.md setup, testing, troubleshooting
  decisions/     architecture decision records
```

## Quick start (Docker)

```bash
docker compose up --build
```

- Web: http://localhost:3000 (the browser only ever calls same-origin `/api/v1`;
  the Next.js server proxies to the API container)
- API: http://localhost:8000 · OpenAPI: http://localhost:8000/api/docs

The demo workspace seeds itself with a **clearly-synthetic** payslip document and
screens it end-to-end (extraction → classification → rules), so the workflow is
inspectable immediately.

## Quick start (local dev)

Backend (Python 3.12):

```bash
cd apps/api
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp ../../.env.example .env   # optional; defaults work for local dev
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend (Node 22):

```bash
cd apps/web
npm install
npm run dev   # http://localhost:3000, proxies /api/v1 to 127.0.0.1:8000
```

Authentication modes (env `AUTH_MODE`):
- `demo` (default) — virtual demo principal, no login, synthetic-data workspace.
- `required` — organisational users + roles (`admin`/`inspector`/`viewer`),
  HttpOnly cookie sessions, bootstrap admin via `BOOTSTRAP_ADMIN_*` env vars.

## Optional local AI

Set `OLLAMA_MODEL` (and `OLLAMA_BASE_URL` if not default) to enable AI screening
with a **local** Ollama model — document text never leaves the deployment host.
If the model is unavailable, deterministic screening continues unaffected and the
API reports AI status honestly (`disabled` / `unavailable`).

## Document storage

Uploads live behind a pluggable `DocumentStore` interface:

- `STORAGE_BACKEND=local` (default): local disk for development and tests only
  (production startup refuses it).
- `STORAGE_BACKEND=s3`: any private S3-compatible bucket (AWS S3, MinIO,
  Cloudflare R2). Objects are **private by default**, keys are
  server-generated, downloads stream through the authorised API (short-lived
  presigned redirects only if you enable `S3_PRESIGNED_DOWNLOADS`), and
  credentials are read from the environment — never hard-coded, never exposed
  to the frontend.

See [.env.example](.env.example) for the `S3_*` variables and
[docs/deployment.md](docs/deployment.md) for production setup.

## Malware scanning

Uploads can pass through an optional malware-scan stage before any bytes are
stored or processed:

- `MALWARE_SCAN_MODE=off` (default, local/demo): uploads are marked
  `scan_status=skipped` — never claimed clean — and production boot refuses to
  run with scanning off.
- `MALWARE_SCAN_MODE=enforcing`: every upload is streamed to a ClamAV daemon
  (`CLAMD_HOST`, default port `3310`). Infected files are rejected and never
  stored; if the scanner is unreachable, times out or errors the upload is
  blocked (fail-closed) and reported via `/api/v1/health`.

See [security baseline](docs/security/security.md) for the control detail.

## Quality gates

Every push runs GitHub Actions:

- API: ruff lint · Alembic migration up/down/up against PostgreSQL 17 ·
  full pytest suite (unit + integration + security) · integration suite against
  PostgreSQL · dependency audit
- Web: eslint · `tsc --noEmit` · production build
- Containers: build all images and smoke-test health, demo seed and OpenAPI

## Documentation

- [Architecture overview](docs/architecture/overview.md)
- [API contract](docs/architecture/api-contract.md) (live OpenAPI at `/api/docs`)
- [Data model](docs/architecture/data-model.md)
- [Document pipeline](docs/architecture/pipeline.md)
- [Security baseline](docs/security/security.md) and [threat model](docs/security/threat-model.md)
- [AI governance](docs/compliance/ai-governance.md)
- [Deployment](docs/deployment.md) · [Development & testing](docs/development.md)
- [Decision records](docs/decisions/adr.md)

## Production security gate

Before connecting real worker or establishment data: approved identity provider
integration, durable PostgreSQL + private object storage with encryption/KMS,
malware scanning, centralised secrets, monitoring/alerting, backups, retention
and deletion controls, and a formal security/privacy review. The codebase is
structured for these (tenancy, roles, audit, migrations, storage abstraction) —
see [docs/deployment.md](docs/deployment.md) for the exact checklist.
