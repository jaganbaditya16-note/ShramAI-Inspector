# Threat Model

## Assets

Uploaded labour documents · extracted text/evidence · inspection cases · findings
and review decisions · audit history · credentials/sessions · rule/model provenance.

## STRIDE-aligned threats and controls

| Threat | Vector | Control (status) |
|---|---|---|
| Spoofing | stolen session cookies | HttpOnly + SameSite + Secure; token hashes only; revocation on logout ✔ |
| Spoofing | credential guessing | Argon2id; uniform failures; auth rate limit ✔; MFA = IdP policy when using SSO |
| Spoofing | SSO code/CSRF abuse (state/nonce forgery, code replay) | OIDC PKCE + signed single-use state cookie + query-state binding + nonce-bound ID-token validation ✔ (tested) |
| Spoofing | account takeover via federated link | verified-email-only linking; unverified emails get isolated accounts ✔ (tested) |
| Tampering | finding/review forgery | server-side role checks; reviewer + timestamp stamping; audit trail ✔ |
| Tampering | malicious file alters parser | magic/EOF validation; bounded extraction; parser errors contained ✔ |
| Tampering | malware uploaded then distributed/stored | pre-storage malware scan stage (clamd INSTREAM); infected → rejected, never stored or processed; scanner down ⇒ fail-closed (upload blocked) ✔ (tested) |
| Repudiation | "I never confirmed that" | append-only audit events with actor + request id ✔ |
| Information disclosure | IDOR / cross-tenant reads | org-scoped queries everywhere; indistinguishable 404s ✔ (tested) |
| Information disclosure | predictable document URLs | server-generated keys; authorised download endpoint re-checks access ✔ |
| Information disclosure | stored files reached directly / cross-tenant | objects private by default, no public URLs, keys never exposed; downloads re-check org-scoped access; presigned URLs (opt-in) are short-lived ✔ (tested) |
| Information disclosure | log leakage | structured logs carry ids/status only; document text never logged ✔ |
| Information disclosure | prompt/content exfiltration via AI | local-only provider by default; bounded input; no third-party calls ✔ |
| DoS | huge uploads / deep PDFs / OCR storms | size caps, page caps, OCR page+DPI bounds, worker semaphore, body limit ✔ |
| DoS | request floods | per-IP sliding windows with Retry-After ✔; multi-instance = gateway |
| Elevation of privilege | role bypass | role rank checks per endpoint; admin-gated bootstrap ✔ |
| Prompt injection | instructions inside documents | untrusted delimiting; schema validation; grounding rejection; findings never auto-confirm ✔ (tested) |
| SQL injection | — | SQLAlchemy bound parameters only; no string SQL ✔ |
| XSS | stored text rendered in UI | React auto-escaping; no `dangerouslySetInnerHTML` anywhere ✔ |
| CSRF | cookie misuse cross-site | SameSite=Lax + Origin check on unsafe methods ✔ |
| Path traversal | storage key manipulation | strict key shape + root confinement (tested) ✔ |

## Residual risks (documented, accepted for current stage)

- In-process rate limiting is per-instance; use a gateway/Redis when scaling out.
- Document storage defaults to local disk for development; production must set
  `STORAGE_BACKEND=s3` (startup enforces this) and enable provider-side
  encryption at rest plus bucket public-access blocking. The bucket itself and
  its IAM credentials are deployment concerns.
- Malware scanning defaults to `off` for local/demo development and must be
  enabled (`MALWARE_SCAN_MODE=enforcing` + a reachable clamd host) in
  production; the daemon itself is a deployment concern. Signatures update on
  the clamd side (freshclam), not in this codebase.
- Demo mode (`AUTH_MODE=demo`) is unauthenticated by design and restricted to
  synthetic data operationally; misuse with real documents is a policy violation,
  not a code gap — production deployments must set `AUTH_MODE=required`.
