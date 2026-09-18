# Threat Model

## Assets
- Uploaded labour documents
- Extracted text and evidence
- Inspection cases
- Findings and review decisions
- Audit history
- Configuration and model/rule provenance

## Threats and controls

| Threat | Control |
|---|---|
| Malicious upload | extension + MIME + magic-byte checks, size limits, quarantine/storage boundary |
| Path traversal | server-generated object names and basename-only display names |
| Unauthorized case access | backend authorization boundary; production identity provider required |
| Secret leakage | environment variables, secret scanning, no secrets in logs |
| Prompt injection in documents | extracted document text is treated as untrusted data, never as instructions |
| AI hallucination | provenance requirement, schema validation, deterministic checks, human review |
| Data exposure | private storage, short-lived access, data minimization, retention policy |
| Audit tampering | append-oriented audit events; production database controls and restricted write access |
| Abuse/DoS | upload limits, request limits and production rate limiting |
| Incorrect legal conclusion | wording restricted to screening/findings; no autonomous enforcement |

## Production gate

Before handling real worker data, add an approved identity provider, database migrations, malware scanning, encryption/KMS controls, centralized secrets, monitoring, backup/restore testing, formal retention/deletion policy and security/privacy review.
