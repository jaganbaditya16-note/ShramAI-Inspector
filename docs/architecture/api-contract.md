# API Contract

Base path: /api/v1

## Health
GET /health

Example response: { status: ok, version: 0.1.0 }

## Cases
POST /cases
GET /cases
GET /cases/{case_id}

## Documents
POST /cases/{case_id}/documents
POST /documents/{document_id}/process
GET /documents/{document_id}/extractions

## Checks and findings
POST /cases/{case_id}/checks
GET /cases/{case_id}/findings
PATCH /findings/{finding_id}

## Reports
POST /cases/{case_id}/report

Use a consistent JSON error shape with code, message and request_id.
