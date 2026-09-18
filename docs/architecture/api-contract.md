# API Contract (v1)

Base path `/api/v1`. Live OpenAPI: `/api/openapi.json` · Swagger: `/api/docs`.

## Conventions

- **Success**: resource JSON (`201`/`200`), uploads return `202` with `{document, job, message}`.
- **Errors**: always `{"error": {"code", "message", "request_id", "details"?}}`.
  Codes: `validation_failed`, `unauthorized`, `forbidden`, `not_found`, `conflict`,
  `payload_too_large`, `rate_limited`, `upload_rejected`, `extraction_failed`,
  `internal_error`.
- **Pagination**: `?limit` (1–100, default 20) `&offset`; list responses carry
  `meta: {total, limit, offset}`.
- **Correlation**: every response carries `X-Request-ID` (client-supplied IDs are
  honoured after sanitation).
- **Auth**: `AUTH_MODE=demo` injects a virtual demo principal; `required` demands
  the HttpOnly session cookie (`POST /auth/login`). Roles: `viewer` (read),
  `inspector` (workflow), `admin`.

## Endpoints

### Health
- `GET /health` — status, version, app env, auth mode, AI provider status.

### Auth (required mode)
- `POST /auth/login` `{email, password}` → sets HttpOnly session cookie.
- `POST /auth/logout` — revokes the session.
- `GET /auth/me` — current principal.

### Cases
- `GET /cases?status&search&limit&offset`
- `POST /cases` `{title, establishment_name?, establishment_reference?, notes?}` (inspector)
- `GET /cases/{id}` · `PATCH /cases/{id}` (fields + status transitions; inspector)
- `DELETE /cases/{id}` — soft delete (inspector)

### Documents
- `POST /cases/{id}/documents` multipart `file` (inspector) → `202` + job;
  processing is asynchronous (`PIPELINE_MODE=background`, default) or in-request (`inline`).
- `GET /cases/{id}/documents?limit&offset`
- `GET /documents/{id}` — status polling (document + latest job).
- `POST /documents/{id}/reprocess` (inspector) → `202`; review decisions on matching
  evidence are preserved.
- `GET /documents/{id}/download` — authorised stream of the original file.

### Findings
- `GET /cases/{id}/findings?status&severity&origin&document_id&sort&limit&offset`
  (`sort`: `-created_at` | `created_at` | `-severity` | `severity` | `confidence`)
- `PATCH /findings/{id}` `{status: confirmed|dismissed|needs_review, note?}` (inspector)

### Reports
- `POST /cases/{id}/report` (inspector) — immutable scorecard snapshot.
- `GET /cases/{id}/report` — latest snapshot (`409 conflict` if none).

### Audit & dashboard
- `GET /cases/{id}/audit?action&limit&offset`
- `GET /dashboard/summary` — SQL-aggregated org counters + recent activity.

## Versioning

The `/v1` prefix is reserved for compatibility. Breaking changes would ship as
`/v2` alongside v1; additive fields are not breaking.
