# Architecture Overview

Browser -> Next.js Web -> FastAPI API -> application services -> PostgreSQL/object storage/AI services.

Document path:
Upload -> validation -> quarantine -> OCR/document parsing -> normalized extraction -> evidence index -> rules engine + RAG analysis -> findings -> human review -> report.

## Service boundaries

### Web
UX, authentication session handling, API calls, accessibility, upload progress, evidence viewer and review workflows.

### API
Authorization, validation, case/document lifecycle, orchestration, audit events and stable API contracts.

### OCR/document processing
PDF/image normalization, OCR, page segmentation and extraction with page/region provenance.

### Rules
Deterministic checks. Rules are versioned and produce structured reasons and required evidence.

### AI
Extraction assistance, retrieval and prioritization. AI output is schema-constrained, validated, and never authoritative by itself.

### Persistence
PostgreSQL stores metadata, findings, review decisions and audit events. Object storage holds encrypted document objects.

## Trust boundaries

1. Untrusted uploaded file -> quarantine scanner.
2. Browser -> authenticated API.
3. AI model -> schema validation.
4. External knowledge -> allowlisted/versioned sources.
5. Human review -> report finalization.

## Demo mode

Use synthetic/redacted documents only. Production government integrations require explicit authorization, security review, contractual controls and approved APIs.
