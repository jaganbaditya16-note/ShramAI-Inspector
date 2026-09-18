# API

FastAPI backend for the ShramAI Inspector prototype.

Implemented responsibilities:
- case lifecycle and synthetic demo case
- PDF/PNG/JPEG validation and upload
- digital PDF text extraction
- scanned-PDF and image OCR
- deterministic screening rules
- optional Ollama analysis with strict schema validation
- evidence-linked findings and human review states
- audit events
- screening scorecard and dashboard summary

The Vercel container includes Tesseract and PDFium. Durable production deployments should provide a managed PostgreSQL database and private object storage instead of the demo SQLite/local filesystem defaults.
