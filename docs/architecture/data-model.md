# Data Model

All tables are organisation-scoped (`org_id` FK). UUID primary keys (stored as
36-char strings for cross-database portability). Timestamps are timezone-aware
UTC. Migrations live in `apps/api/alembic/versions/`.

```
Organization 1─* User 1─* AuthSession
Organization 1─* Case 1─* Document 1─* Finding
                      ├─* ProcessingJob
                      ├─* ModelRun
                      ├─* Report
                      └─* AuditEvent (also org-scoped, case optional)
```

## Entities

| Table | Purpose |
|---|---|
| `organizations` | Tenant root. Every inspection object belongs to one. |
| `users` | Organisational accounts: email, name, Argon2id hash, role (`admin`/`inspector`/`viewer`), active flag, last login. |
| `auth_sessions` | Cookie sessions. Only the SHA-256 hash of the opaque token is stored; expiry + revocation tracked. |
| `cases` | Inspection container: display code (`SH-YYYY-XXXXXX`), title, establishment identity, status (`draft`→`in_review`→`closed`), notes, soft delete (`deleted_at`). |
| `documents` | Uploaded file metadata + processing state: sanitised filename, private storage key, content type, size, sha256, status (`queued`→`processing`→`processed`/`failed`), page count, extracted text, page map (character offsets per page), classified doc type + confidence. |
| `processing_jobs` | One pipeline run per document: status, attempts, timings, finding counts, error. Enables 202-upload + polling and restart recovery. |
| `findings` | Screening results: rule id + version, origin (`rule`/`ai`), severity, review state machine (`needs_review`→`confirmed`/`dismissed`, reversible), explanation, evidence kind (`quote`/`absence`), evidence quote + hash + page + char anchors, confidence, AI metadata, review attribution. |
| `model_runs` | AI governance trace: provider, model, status, prompt version, latency, findings produced/rejected-ungrounded. |
| `reports` | Immutable scorecard snapshots (score, risk level, full JSON payload). |
| `audit_events` | Append-only trail: actor, action, JSON detail (ids only — never document text), request id. |

## Indexes

Foreign keys and all hot filters are indexed, e.g. `findings(case_id, status)`,
`documents(case_id, status)`, `cases(org_id, deleted_at)`,
`audit_events(org_id, created_at)`, unique `auth_sessions(token_hash)`.

## Deliberate omissions

- No `rules` table: the rule registry is versioned code (tested, reproducible);
  `rule_version` is stamped on every finding and report. A DB table would add sync
  drift without traceability benefit.
- No notifications table yet: no email/push channel exists; the audit trail plus
  dashboard covers current needs (recorded in ADR).
