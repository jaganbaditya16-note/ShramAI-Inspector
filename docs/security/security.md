# Security and Privacy Baseline

- TLS for network transport.
- Secrets only through environment/secret storage; never commit credentials.
- Strict extension, MIME, magic-byte, size and page-count validation.
- Malware scanning/quarantine before processing.
- Private object storage; documents are never public.
- Server-side tenant/case authorization.
- Audit login, case changes, document actions, processing, finding changes and report generation.
- Never log raw documents or secrets.
- Short-lived signed URLs for evidence access.
- Rate limits and upload/request size limits.
- AI prompts and outputs are isolated from executable code paths.
- No autonomous enforcement action.
- Configurable retention/deletion policy.
- Synthetic data for public demos.

## AI safety

AI-generated findings require structured-output validation, provenance to source evidence, deterministic validation where applicable, confidence/uncertainty state, and human review before report finalization.
