# API Contract

Base path: `/api/v1`

## Health
- `GET /health` — returns API status and version.

## Cases
- `POST /cases` — create an inspection case.
- `GET /cases` — list cases; initializes the synthetic `DEMO-001` case when the demo database is empty.
- `GET /cases/{case_id}` — fetch a case.

## Documents
- `POST /cases/{case_id}/documents` — upload and immediately process PDF/PNG/JPEG.
- `POST /documents/{document_id}/process` — reprocess an existing document.
- `GET /cases/{case_id}/documents` — list source documents.

## Findings and audit
- `GET /cases/{case_id}/findings` — list findings.
- `PATCH /findings/{finding_id}` — set `accepted`, `rejected` or `needs_review`.
- `GET /cases/{case_id}/audit` — list audit events.
- `GET /dashboard/summary` — aggregate dashboard counters.

## Reports
- `POST /cases/{case_id}/report` — generate a transparent screening scorecard.

## Errors
Errors use FastAPI's standard JSON `detail` response. Production deployments should place the API behind approved authentication/authorization and centralized observability.
