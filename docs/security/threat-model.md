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
| Information disclosure | document text in logs/audit/reports API | canary-based red-team probe asserts extracted text never reaches server logs, audit payloads or report bodies; audit stores sha256 prefix only ✔ (tested) |
| Information disclosure | auth enumeration via audit/behaviour | uniform login failures with dummy-hash timing cover; failed-login audit reasons are never exposed via any API (case audits only) ✔ (tested) |
| DoS | huge uploads / deep PDFs / OCR storms | size caps, page caps, OCR page+DPI bounds, worker semaphore, body limit ✔ |
| DoS | request floods | per-IP sliding windows with Retry-After ✔; multi-instance = gateway |
| Elevation of privilege | role bypass | role rank checks per endpoint; admin-gated bootstrap ✔ |
| Prompt injection | instructions inside documents | untrusted delimiting; schema validation; grounding rejection; findings never auto-confirm ✔ (tested) |
| SQL injection | — | SQLAlchemy bound parameters only; no string SQL ✔ |
| XSS | stored text rendered in UI | React auto-escaping; no `dangerouslySetInnerHTML` anywhere ✔ |
| CSRF | cookie misuse cross-site | SameSite=Lax + Origin check on unsafe methods; allow-list accepts full-origin or bare-host entries for proxied deployments ✔ (tested) |
| XSS (API layer) | reflected/stored payload served as HTML | the API serves JSON only; downloads are `attachment` with sanitised RFC-5987 filenames ✔ (tested) |
| CORS abuse | credentialed cross-origin reads | CORS registered only from an explicit startup allow-list; preflight reflects allow-listed origins exclusively (live-tested) ✔ |
| Path traversal | storage key manipulation | strict key shape + root confinement (tested) ✔ |
| Malicious headers | hostile `X-Request-ID`, filename headers | request ids are validated against a safe charset or regenerated; filenames sanitised (basename, control-char strip, 255 cap) before storage and in `Content-Disposition` ✔ (tested) |

## AI containment (verified)

- Document text is framed as **untrusted data** between explicit delimiters;
  the prompt forbids following instructions found inside it (probe-tested).
- Every AI finding must cite a verbatim quote located in the extracted text
  (whitespace/case-insensitive with bounded prefix fallback); ungrounded
  findings are rejected and counted on the model run.
- Malformed or hostile provider output maps to a contained `error`/`unavailable`
  state with zero persisted findings; AI findings always start as
  `needs_review` and no automated path can confirm them.
- The knowledge corpus is operator-controlled local files with provenance;
  uploaded documents never enter it (retrieval-poisoning surface closed).

## OIDC boundary (verified)

Exact issuer match before any discovered endpoint is used; RS-family/ES
allow-list (rejects `none` and symmetric confusion); JWKS `kid` match; `aud`,
`exp`/`iat`, required-claims and nonce binding; signed single-use state cookie.
Post-login redirect is a fixed, configured same-origin relative path (open
redirects rejected at config validation).

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
- `/api/docs`, `/api/redoc` and `/api/openapi.json` are public by design (the
  API is authenticated; the schema discloses endpoint shapes only). Operators
  who want them hidden should block them at the gateway.
- These controls are technical measures only. They do not constitute legal,
  regulatory or compliance certification of the platform; human review of every
  finding remains mandatory by design.
