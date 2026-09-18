# Development Guide

## Prerequisites

Python 3.12 (3.11 works) · Node 22 · Tesseract (optional — enables the OCR
fallback; everything else runs without it) · PostgreSQL 17 (optional locally).

## Backend

```bash
cd apps/api
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp ../../.env.example .env          # optional
alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

OpenAPI: http://localhost:8000/api/docs

## Frontend

```bash
cd apps/web
npm install
API_ORIGIN=http://127.0.0.1:8000 npm run dev   # http://localhost:3000
```

## Commands

| Task | Command (dir) |
|---|---|
| API tests | `pytest -q` (apps/api) |
| API lint | `ruff check app tests` (apps/api) |
| Migration check | `alembic upgrade head && alembic downgrade base && alembic upgrade head` |
| Web lint | `npm run lint` (apps/web) |
| Web types | `npm run typecheck` (apps/web) |
| Web build | `npm run build` (apps/web) |
| Full stack | `docker compose up --build` (root) |

## Test layout

- `tests/unit/` — rules, scoring, validation/storage, extraction, classification,
  AI grounding/schema, retrieval, synthetic PDF
- `tests/integration/` — health/seed, cases, document pipeline (inline +
  background), findings/review, reports/audit, dashboard
- `tests/integration/test_security.py` — IDOR, tenant isolation, auth-required
  mode, login enumeration resistance, rate limits, headers, prompt-injection

Conftest pins env (inline pipeline, isolated SQLite/storage, rate limiting off)
before importing the app; each test gets a fresh database.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Web can't reach API in dev | start API on 8000 first; dev server proxies `API_ORIGIN` (default `http://127.0.0.1:8000`) |
| OCR never runs | Tesseract missing — install the binary; PDFs still extract via text layer |
| `processing was interrupted by a service restart` | expected after a kill mid-pipeline; use "Reprocess" on the document |
| 401 on every call after switching `AUTH_MODE` | old cookies are invalid; log in again or clear cookies |
| Port 8000 busy | `uvicorn ... --port 8001` and start web with `API_ORIGIN=http://127.0.0.1:8001` |
| Demo case missing | `AUTH_MODE` must be `demo` (seeding is disabled in `required` mode) |

## Conventions

- Conventional commits (`feat:`, `fix:`, `refactor:`, `security:`, `test:`,
  `docs:`, `chore:`).
- Backend: ruff (lint+format rules) must pass; service layer holds domain logic;
  routers stay thin; every bug fix lands with a regression test.
- Frontend: strict TS; no `any`; design-system primitives before ad-hoc styles;
  every motion gated by `prefers-reduced-motion`.
