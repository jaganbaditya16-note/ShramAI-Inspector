# ShramAI Inspector

AI-assisted labour-code compliance inspection platform for Shram Suvidha.

## Mission
ShramAI Inspector helps authorized inspectors review labour compliance documents using a hybrid architecture:

**Document AI/OCR -> structured extraction -> deterministic rule engine -> retrieval-augmented evidence -> anomaly/risk detection -> explainable findings -> human verification -> audit-ready report**

The system is an assistive tool, not an autonomous legal decision-maker. Findings are recommendations for authorized human review.

## Problem Statement
Digital Shram Sankalp — Problem Statement #5: AI-Driven Smart Inspection System for Labour Code Compliance for Shram Suvidha Portal.

## Design principles
- Human-in-the-loop for every substantive compliance finding.
- Evidence-first: every finding links to the document/page/field used.
- Deterministic rules for hard checks; AI for extraction, retrieval and prioritization.
- Never invent legal requirements. Unknown or ambiguous checks are marked Needs Review.
- Data minimization, encryption in transit/at rest, role-based access, audit logs and configurable retention.
- No final legal conclusion, penalty, prosecution or enforcement action is generated automatically.
- Confidence and provenance are displayed with each finding.
- Designed for multilingual and scanned-document workflows.
- Public demo data must be synthetic/redacted.

## MVP flow
1. Sign in as an authorized demo inspector.
2. Create an inspection case.
3. Upload supported labour documents (PDF/JPG/PNG).
4. Run OCR/document extraction.
5. Review extracted fields and correct them when necessary.
6. Run compliance checks.
7. Review findings with evidence and confidence.
8. Assign severity and disposition during human review.
9. Generate a signed/auditable inspection report.
10. View case analytics.

## Monorepo structure
```
apps/
  web/       # Next.js frontend
  api/       # FastAPI backend
services/
  ocr/       # OCR/document preprocessing
  rules/     # deterministic compliance rules
  ai/        # RAG, extraction and risk analysis
packages/
  contracts/ # shared API schemas/types
  ui/        # shared UI primitives
  config/    # shared configuration
data/
  demo/      # synthetic sample documents and fixtures
docs/
  architecture/
  security/
  compliance/
scripts/
tests/
```

## Planned API
- `POST /api/v1/cases`
- `GET /api/v1/cases`
- `POST /api/v1/cases/{case_id}/documents`
- `POST /api/v1/documents/{document_id}/process`
- `GET /api/v1/documents/{document_id}/extractions`
- `POST /api/v1/cases/{case_id}/checks`
- `GET /api/v1/cases/{case_id}/findings`
- `PATCH /api/v1/findings/{finding_id}`
- `POST /api/v1/cases/{case_id}/report`
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/health`

## Non-goals for MVP
- Direct production integration with government systems without authorization.
- Automatic legal adjudication.
- Facial recognition or worker surveillance.
- Unverified personal-data enrichment.
- Autonomous enforcement decisions.

## Quality gates
Before demo/submission:
- frontend and backend run independently and together
- uploaded documents never expose secrets
- every AI finding has provenance
- deterministic rules have tests
- API validation and error handling are covered
- audit events are recorded
- synthetic demo data is reproducible
- README includes setup and architecture