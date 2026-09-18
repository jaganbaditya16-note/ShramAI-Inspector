# Security and Privacy Baseline

## Implemented in the prototype
- Server-generated upload names and basename-only display names.
- PDF/PNG/JPEG extension, MIME, magic-byte and size validation.
- Request-body size limit.
- Optional bearer token dependency for protected API routes.
- Security response headers.
- Document text is treated as untrusted prompt data.
- AI output is schema-validated before findings are stored.
- Audit events are recorded for case/document/review activity.
- Public demo guidance requires synthetic or redacted data.
- No autonomous enforcement action is generated.

## Required before production
- TLS termination and approved identity provider.
- Server-side tenant/case authorization tied to authenticated identities.
- Malware scanning/quarantine before OCR.
- Private object storage with encryption/KMS.
- Centralized secrets and key management.
- Rate limiting and abuse monitoring.
- Short-lived evidence access URLs.
- Configurable retention/deletion and backup/restore testing.
- Centralized logs, alerts and security monitoring.
- Formal DPDP/privacy/security review and approved government integration controls.

## AI safety
AI-generated findings require structured-output validation, provenance to source evidence, deterministic validation where applicable, confidence/uncertainty state, and human review before report finalization.
