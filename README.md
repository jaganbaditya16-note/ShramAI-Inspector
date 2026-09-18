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
1. Open the demo inspector workspace.
2. Create an inspection case or use the synthetic demo case.
3. Upload supported labour documents (PDF/JPG/PNG).
4. Extract text from digital PDFs and OCR scanned PDFs/images.
5. Run deterministic screening checks and optional local AI analysis.
6. Review findings with evidence and confidence.
7. Accept or dismiss findings during human review.
8. Generate a transparent screening scorecard.
9. Export the scorecard as JSON.
10. View documents and audit activity.

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

## Implemented API
- `GET /api/v1/health`
- `GET /api/v1/cases`
- `POST /api/v1/cases`
- `GET /api/v1/cases/{case_id}`
- `POST /api/v1/cases/{case_id}/documents`
- `POST /api/v1/documents/{document_id}/process`
- `GET /api/v1/cases/{case_id}/documents`
- `GET /api/v1/cases/{case_id}/findings`
- `PATCH /api/v1/findings/{finding_id}`
- `GET /api/v1/cases/{case_id}/audit`
- `GET /api/v1/dashboard/summary`
- `POST /api/v1/cases/{case_id}/report`

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

## Current MVP status

The repository contains a working reference implementation for:
- Next.js inspector workspace
- FastAPI API
- PostgreSQL/SQLAlchemy persistence
- secure PDF/image upload validation
- PDF text extraction, scanned-PDF OCR and image OCR
- versioned deterministic screening rules
- optional local Ollama analysis with schema validation
- provenance-aware local knowledge retrieval
- evidence-linked findings
- human review states
- audit events
- report generation
- Docker Compose
- CI checks

### Run locally with Docker

```bash
docker compose up --build
```

Open:
- Web: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/api/docs

### Optional local AI

Set `OLLAMA_MODEL` to an installed local model and keep `OLLAMA_BASE_URL` pointed at the local Ollama service. If no model is configured or the model is unavailable, deterministic screening continues and the API reports the AI status rather than failing the inspection.

### Production security gate

Before real government or worker data is connected, replace demo authentication with an approved identity provider, use database migrations, private object storage/KMS, malware scanning, centralized secrets, production rate limiting, monitoring, backups, retention/deletion controls and formal security/privacy review.

## Submission positioning

ShramAI Inspector is designed around Digital Shram Sankalp Problem Statement #5. The prototype demonstrates the requested document-analysis workflow while deliberately keeping legal determination and enforcement decisions with authorized human reviewers.

## Verification

Every push is checked by GitHub Actions for backend tests and frontend production build. Review the latest workflow result before production deployment.


## Single-domain Vercel deployment

The repository includes a root `vercel.json` configured for Vercel Services:
- `web`: Next.js inspector dashboard
- `api`: containerized FastAPI backend with Tesseract OCR
- `/api/*`: routed to FastAPI
- `/*`: routed to Next.js

This keeps the public product on one domain. Vercel Services requires the Vercel project framework to be set to **Services**. Vercel's current documentation describes this model for a Next.js frontend plus FastAPI backend on one deployment URL.

For the public prototype, the backend tolerates blank environment variables and uses a temporary SQLite database under Vercel's ephemeral filesystem. This is demo-only: Vercel containers are stateless, so durable PostgreSQL and private object storage must be configured before handling real worker records. The API container includes Tesseract plus PDFium so image OCR and scanned-PDF OCR can run in the deployed prototype.

The browser uses the same-origin `/api/v1` path in production, so it does not call `localhost:8000`.
