# MVP Implementation

## Demonstration scenario

Use a synthetic labour record containing:
- employee identifiers replaced with synthetic IDs
- attendance/working-hour entries
- wage/pay entries
- one intentionally incomplete section

### Demo sequence

1. Create an inspection case.
2. Upload the synthetic record.
3. Process it.
4. Show extracted text status.
5. Show screening findings.
6. Open evidence for each finding.
7. Accept or reject a finding.
8. Generate the report draft.
9. Show that the report states the output is AI-assisted screening and requires authorized human review.

## What is real in the MVP

- API calls between browser and FastAPI.
- Persistent case/document/finding data through SQLAlchemy.
- PDF text extraction.
- Image OCR when Tesseract is installed.
- File size/type validation.
- Deterministic screening rules.
- Human review state transitions.
- Audit event persistence.
- Report JSON generation.

## What is intentionally a later integration

- Government production APIs.
- Official legal-rule corpus ingestion.
- Enterprise identity provider.
- Production object storage/KMS.
- Malware scanning service.
- Advanced ML anomaly model.
- Production RAG model/provider.

This separation prevents a demo from pretending that unauthorized access to government systems or production legal data already exists.
