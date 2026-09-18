# Data Model

Case -> many Documents
Case -> many Findings
Case -> many AuditEvents
Document -> many Findings

## Case
Inspection container and establishment reference.

## Document
Metadata, private storage path, processing status and extracted text.

## Finding
A versioned screening result linked to a document, with evidence, explanation, confidence and human review state.

## AuditEvent
Append-oriented record of important workflow actions.

Production should use database migrations rather than startup schema creation.
