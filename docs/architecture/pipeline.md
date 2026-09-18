# Document Processing Pipeline

```
UPLOAD → FILE VALIDATION → STORAGE → REGISTRATION (202 + job)
       → EXTRACTION (text/OCR, bounded) → NORMALISATION + PAGE MAP
       → CLASSIFICATION → RULE ENGINE → OPTIONAL GROUNDED AI
       → FINDINGS (evidence-anchored) → CASE/AUDIT UPDATE
       → HUMAN REVIEW → REPORT SNAPSHOT
```

## Stage contract

| Stage | Implementation | Failure behaviour |
|---|---|---|
| Validation | extension + MIME + magic bytes + PDF EOF marker, streaming size bound | `400 upload_rejected` / `413`; nothing persisted |
| Malware scan | validate → scan → store. `MalwareScanner` interface; ClamAV clamd INSTREAM adapter streams the upload in 64 KiB chunks. `MALWARE_SCAN_MODE=off` (dev/demo default) records `scan_status=skipped` — it never claims clean; `enforcing` requires a configured scanner and is fail-closed | infected → `400 infected_document`, document `rejected` (signature + sha256 kept, bytes never stored); unavailable/timeout/error → `503`, oversize-for-scanner → `413`; nothing persisted; audit event for every verdict. Pipeline also refuses any document without `scan_status ∈ {clean, skipped}` (job fails + audit `document_processing_blocked`) |
| Storage | `DocumentStore` interface — local disk (dev) or private S3-compatible bucket (production) behind `STORAGE_BACKEND`; UUID date-partitioned keys validated against a strict shape; sha256 preserved; objects private with no public URLs; failed registrations clean up their object; storage failures → `503 storage_unavailable`, nothing persisted |
| Registration | `documents` row (`queued`) + `processing_jobs` row, audit event in the same transaction | — |
| Extraction | pypdf text layer per page; scanned PDFs → pypdfium2 raster + Tesseract OCR (page/scale bounded); images → PIL verify + OCR. Runs in a worker thread. | `extraction_failed` → document `failed` with safe message + audit |
| Normalisation | whitespace normalisation with offset-preserving page map (`[{page,start,end}]`) | warnings recorded on job detail |
| Classification | deterministic keyword-weighted doc type (`payslip`/`attendance`/`unknown`) + confidence | — |
| Rule engine | versioned registry; rules declare applicable doc types; violations carry quote+page+offset or `absence` | deterministic; covered by unit tests |
| AI (optional) | provider protocol → local Ollama; untrusted-data delimiters; strict JSON schema; evidence grounding (whitespace/case-insensitive verbatim match with bounded prefix fallback) | provider unavailable → `model_runs.status=unavailable`, job continues; ungrounded findings rejected + counted |
| Findings write | decision-preserving replace: reviewed findings matched by `(rule_id, evidence_hash)` survive reprocessing | — |
| Finalisation | document `processed`, job `succeeded` with timings, case → `in_review`, audit event | unexpected errors → document/job `failed` with safe message; traceback only in logs |

## Operational properties

- **202 + polling**: the client gets an immediate acknowledgement and polls
  `GET /documents/{id}`; no long-blocking uploads.
- **Bounded concurrency**: in-process scheduler with a semaphore
  (`PIPELINE_CONCURRENCY`, default 2).
- **Inline mode**: `PIPELINE_MODE=inline` runs the pipeline inside the request for
  environments where background work cannot outlive the request.
- **Restart recovery**: at startup, jobs stuck in `queued`/`running` are marked
  failed with "interrupted by service restart" — clients can reprocess.
- **Deletion safety**: retention purges remove the storage object before the
  document row; documents with queued/running jobs are never purged, and the
  pipeline fails safely when a document vanishes mid-flight (deleted data is
  never revived). See [data lifecycle](data-lifecycle.md).
- **Limits**: `MAX_PDF_PAGES_TEXT`, `MAX_PAGES_OCR`, `OCR_DPI_SCALE`,
  `MAX_EXTRACT_CHARS`, `MAX_UPLOAD_MB` — tuned to bound memory and CPU against
  hostile or accidental large inputs.
