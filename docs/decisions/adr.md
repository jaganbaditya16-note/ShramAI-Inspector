# Architecture Decision Records

## ADR-001 — Layered monolith over microservices

**Status**: accepted (2026-09)

The platform ships as one API service + one web service. Extraction, rules, and AI
already live behind service protocols (`DocumentStore`, `AIProvider`, rule
registry) and could be extracted into workers, but separate deployables would add
orchestration cost without a scaling need at current volumes. Job tracking is
DB-persisted so a queue/worker split later reuses the same states.

## ADR-002 — Background pipeline with DB-persisted jobs (not Celery/Redis)

**Status**: accepted (2026-09)

Uploads return 202 and processing runs in-process with bounded concurrency; state
lives in `processing_jobs`. A broker adds a second stateful system to operate —
unjustified while one container serves the demo and small deployments. The job
table + recovery semantics mean a Celery/RQ worker can adopt the same rows later
without API changes. `PIPELINE_MODE=inline` covers platforms that cannot run
background tasks.

## ADR-003 — Organisations + roles now, SSO later

**Status**: accepted (2026-09)

Real authn (Argon2id, sessions, roles) and hard tenancy (org-scoped queries) are
in the core because retrofitting tenancy is expensive and IDOR risks are severe.
Government SSO/identity-provider integration is a deployment-stage concern that
plugs into `get_principal`.

## ADR-004 — Evidence grounding as a hard gate for AI findings

**Status**: accepted (2026-09)

AI findings are stored only when their evidence quote matches the extracted text
(whitespace/case-insensitive verbatim, bounded prefix fallback). Ungrounded output
is counted on `model_runs`, never stored. This converts hallucination from a
review burden into a measurable, rejected-by-construction event. Trade-off: the
model must quote exactly; prompts enforce this and tests cover it.

## ADR-005 — Rules as versioned code, not DB rows

**Status**: accepted (2026-09)

The rule registry is pure and unit-tested; `RULE_VERSION` is stamped on findings
and reports. A `rules` table would introduce DB/code drift with no operational
benefit while the rule set is curated by developers. Revisit only if non-developers
must author rules.

## ADR-006 — Cookie sessions over bearer tokens for the SPA

**Status**: accepted (2026-09)

The web app always calls the API same-origin (server proxy/rewrite), so HttpOnly
cookies beat localStorage tokens on XSS resistance. SameSite=Lax plus an Origin
check on unsafe methods covers CSRF for this topology. CORS stays allow-listed
for explicit cross-origin tooling only.

## ADR-007 — Synthetic demo corpus, empty-by-default knowledge base

**Status**: accepted (2026-09)

The repo must never ship unverified legal text. `data/knowledge/` accepts only
approved, versioned, provenance-carrying markdown (template + README included);
the demo corpus is clearly-labelled synthetic material so retrieval and AI flows
are demonstrable without fabricating authority.

## ADR-008 — Pluggable document storage: local disk (dev) + private S3-compatible object store (production)

**Status**: accepted (2026-09)

The application depends on a narrow `DocumentStore` interface (save / get /
exists / delete / stat / open_path / optional presign), not on local disk.
`STORAGE_BACKEND` selects the implementation: `local` (development/tests,
unchanged behaviour) or `s3` (any S3-compatible private bucket via boto3).
Decisions embedded in this choice:

- **Private by default, no public URLs.** Downloads stream through the
  authorised API endpoint; a presigned-GET redirect exists only when explicitly
  enabled and is short-lived (default 300 s, capped at 1 h).
- **Server-generated keys only**, validated against a strict shape in every
  backend method — path traversal is impossible by construction.
- **Fail-safe semantics**: upload-write failures → `503 storage_unavailable`
  with nothing persisted; registration failures remove the just-written object;
  delete failures keep the document row; missing objects → safe 404.
- **Startup enforcement**: `s3` without bucket/credentials refuses to boot;
  `local` refuses to boot in production (demo-grade durability is a config
  error, not a silent default).
- boto3 is the one new production dependency (necessary for S3; lazily used so
  local development never touches it). No AWS SDK defaults are trusted for
  security posture: no public ACLs, SSE optional but configurable.

Consequences: storage provider changes are config-only; retention/lifecycle
rules remain a deployment concern (deferred).

## ADR-009 — Provider-agnostic identity layer; OIDC SSO without replacing the session core

**Status**: accepted (2026-09)

The existing session architecture (opaque cookie token, hashed `auth_sessions`
row, org-scoped roles, IDOR-safe queries) is provider-independent and stays.
A narrow `IdentityProvider` interface (`begin_login` / `complete_login`)
abstracts *identity verification*: the password endpoint is the local provider
and `AUTH_MODE=oidc` adds a standards-based OIDC authorization-code flow with
PKCE. Decisions embedded:

- **No new auth framework** (no Authlib/IdentityModel): PyJWT + the existing
  machinery. Sessions minted by any provider are indistinguishable downstream,
  so RBAC/tenancy/audit rules hold everywhere by construction.
- **Federation binding**: `(idp_issuer, idp_subject)` unique on `users`;
  linking to an existing local account requires a **verified** email claim;
  unverified emails get isolated accounts. Provider `groups`/`role` claims are
  recorded but never auto-map to local roles — privilege escalation via IdP
  claims is a documented non-goal.
- **Flow hardening**: state+nonce+PKCE in an HMAC-signed HttpOnly cookie
  (5 min TTL, single-use, constant-time checks); ID tokens validated against
  JWKS with issuer/audience/nonce/expiry checks; discovery issuer must match
  configuration; provider errors never reach users (one generic message,
  category-only audit reason).
- **Startup enforcement**: `oidc` without issuer/client-id/secret/redirect
  refuses to boot; non-https issuer/redirect outside loopback dev refuses;
  `AUTH_MODE=demo` in production refuses.
- Live SSO against a real IdP is NOT claimed: the flow is verified in tests
  against an in-process RSA-backed fake IdP (discovery/JWKS/token endpoints);
  operator acceptance with the real IdP remains a deployment task.

Consequences: adding SAML/other providers later means implementing
`IdentityProvider`, not touching authorisation code.
