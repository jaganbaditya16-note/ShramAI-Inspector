"""Retention & deletion lifecycle (single service for all destructive logic).

Design (see docs/architecture/data-lifecycle.md):

- **Data inventory**: document originals live in object storage; extracted
  text, page map and all analysis output live inside the ``documents`` row and
  its cascades (findings/evidence, model_runs, processing_jobs); reports hang
  off cases; audit events are standalone rows (no FK) and are **never**
  deleted by retention.
- **Policy** (all defaults are non-destructive, ``0 = never``):
  - ``retention_document_days`` — purge documents N days after upload.
  - ``retention_rejected_document_days`` — rejected/failed documents carry no
    review value and default to a short life.
  - ``retention_case_days`` — soft-deleted cases are hard-purged N days after
    soft-deletion (documents, extracted text, findings, reports, storage
    objects). Active cases are NEVER deleted by this service.
  - ``retention_session_days`` — expired ``auth_sessions`` rows are removed
    (users are untouched).
- **Ordering guarantees**: the storage object is deleted **before** the ledger
  row; if the backend fails, the row stays (the row is what lets us retry —
  deleting it first would orphan the object). A missing object is treated as
  already deleted. All operations are idempotent: sweeps re-run safely.
- **Race safety**: documents with queued/running processing jobs are excluded
  from sweeps; the pipeline itself re-fetches rows and fails safely when a
  document vanished (expired jobs cannot revive deleted data).
- **Tenant safety**: sweeps are instance-level operator functions (admin
  endpoint / startup); user-initiated deletion goes through the org-scoped
  ``get_document_or_404`` path only.
- **Audit**: purge events record ids, verdict categories and sha256 prefixes —
  never document contents; pre-existing audit events survive every purge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.helpers import utcnow
from ..models import AuthSession, Case, Document, ProcessingJob
from .audit_service import record as audit_record
from .storage import StorageError, get_store

logger = logging.getLogger("shramai.retention")

PURGABLE_DOCUMENT_STATUSES = {"rejected", "failed"}


@dataclass
class PurgeReport:
    """Counts from one sweep — safe to return to operators (ids only)."""

    documents_purged: int = 0
    cases_purged: int = 0
    sessions_purged: int = 0
    documents_deferred: int = 0  # storage failures; retried next sweep
    cases_deferred: int = 0
    skipped_active_jobs: int = 0
    errors: list[str] = field(default_factory=list)


# --- policy computation (pure, unit-tested) ------------------------------------------


def document_expiry(created_at: datetime, status: str, *, now: datetime | None = None) -> datetime | None:
    """When this document becomes purge-eligible, or None for "never"."""
    now = now or utcnow()
    if status in PURGABLE_DOCUMENT_STATUSES:
        days = settings.retention_rejected_document_days
        if days <= 0:
            return None
        return created_at + timedelta(days=days)
    days = settings.retention_document_days
    if days <= 0:
        return None
    return created_at + timedelta(days=days)


def case_purge_due(case: Case, *, now: datetime | None = None) -> bool:
    """Only soft-deleted cases ever become purge candidates (never active ones)."""
    if case.deleted_at is None:
        return False
    days = settings.retention_case_days
    if days <= 0:
        return False
    now = now or utcnow()
    return case.deleted_at + timedelta(days=days) <= now


# --- document purge --------------------------------------------------------------------


def purge_document(db: Session, document: Document, *, reason: str, commit: bool = True) -> bool:
    """Hard-delete one document: object first, then rows. Idempotent.

    Returns True when purged, False when deferred (storage failure; the row is
    kept so the next sweep can retry). Audit events are never removed.
    """
    if not document.storage_key:
        # Rejected uploads never stored bytes: row-only purge.
        _delete_document_rows(db, document)
        _audit_purge(db, document, reason)
        if commit:
            db.commit()
        return True
    try:
        get_store().delete(document.storage_key)
    except StorageError:
        logger.warning(
            "event=retention_purge_deferred document=%s reason=storage_error", document.id
        )
        db.rollback()
        return False
    _delete_document_rows(db, document)
    _audit_purge(db, document, reason)
    if commit:
        db.commit()
    return True


def _delete_document_rows(db: Session, document: Document) -> None:
    # findings / model_runs / processing_jobs / extracted text all cascade or
    # live on the document row itself.
    db.delete(document)


def _audit_purge(db: Session, document: Document, reason: str) -> None:
    audit_record(
        db,
        action="retention_document_purged",
        org_id=document.org_id,
        case_id=document.case_id,
        detail={
            "document_id": document.id,
            "sha256": document.sha256[:16],
            "reason": reason,
        },
    )


# --- sweeps ------------------------------------------------------------------------------


def purge_expired_documents(db: Session, *, now: datetime | None = None,
                            limit: int | None = None) -> PurgeReport:
    now = now or utcnow()
    limit = limit or settings.retention_purge_batch
    report = PurgeReport()
    candidates = db.scalars(
        select(Document).order_by(Document.created_at.asc()).limit(limit * 2)
    ).all()
    purged_documents: list[str] = []
    for document in candidates:
        if report.documents_purged + report.documents_deferred >= limit:
            break
        expiry = document_expiry(document.created_at, document.status, now=now)
        if expiry is None or expiry > now:
            continue
        active_jobs = db.scalar(
            select(ProcessingJob.id)
            .where(ProcessingJob.document_id == document.id)
            .where(ProcessingJob.status.in_(("queued", "running")))
            .limit(1)
        )
        if active_jobs is not None:
            report.skipped_active_jobs += 1
            continue
        if document.status in PURGABLE_DOCUMENT_STATUSES:
            reason = "rejected_document_expired"
        else:
            reason = "document_expired"
        if purge_document(db, document, reason=reason):
            report.documents_purged += 1
            purged_documents.append(document.id)
        else:
            report.documents_deferred += 1
    if report.documents_deferred:
        audit_record(
            db, action="retention_purge_failed", org_id=None,
            detail={"deferred": report.documents_deferred, "reason": "storage_error"},
        )
        db.commit()
    return report


def purge_expired_cases(db: Session, *, now: datetime | None = None,
                        limit: int | None = None) -> PurgeReport:
    """Hard-purge soft-deleted cases whose retention elapsed (idempotent)."""
    now = now or utcnow()
    limit = limit or settings.retention_purge_batch
    report = PurgeReport()
    candidates = db.scalars(
        select(Case)
        .where(Case.deleted_at.is_not(None))
        .order_by(Case.deleted_at.asc())
        .limit(limit)
    ).all()
    store = get_store()
    for case in candidates:
        if report.cases_purged + report.cases_deferred >= limit:
            break
        if not case_purge_due(case, now=now):
            continue
        documents = db.scalars(select(Document).where(Document.case_id == case.id)).all()
        pending_objects: list[str] = []
        for document in documents:
            if not document.storage_key:
                continue
            try:
                store.delete(document.storage_key)
            except StorageError:
                pending_objects.append(document.id)
        if pending_objects:
            # Rows stay as the ledger of not-yet-removed objects; retry later.
            report.cases_deferred += 1
            report.errors.append(f"case {case.id}: {len(pending_objects)} objects pending")
            logger.warning(
                "event=retention_case_deferred case=%s pending=%d",
                case.id, len(pending_objects),
            )
            continue
        audit_record(
            db, action="retention_case_purged", org_id=case.org_id, case_id=case.id,
            detail={"case_id": case.id, "code": case.display_code, "documents": len(documents)},
        )
        db.delete(case)  # cascades documents/findings/reports/jobs/model_runs
        report.cases_purged += 1
    if report.cases_purged or report.cases_deferred:
        db.commit()
    return report


def purge_expired_sessions(db: Session, *, now: datetime | None = None) -> int:
    """Remove auth-session rows expired long ago (rows only; users untouched)."""
    now = now or utcnow()
    cutoff = now - timedelta(days=settings.retention_session_days)
    stale = db.scalars(
        select(AuthSession)
        .where(AuthSession.expires_at < cutoff)
        .limit(settings.retention_purge_batch)
    ).all()
    for session in stale:
        db.delete(session)
    if stale:
        db.commit()
    return len(stale)


def run_retention_sweep(db: Session) -> PurgeReport:
    """One bounded sweep: documents → cases → sessions. Cheap, idempotent.

    Every stage is error-isolated with a rollback: retention must never take
    the API down, whatever state the database is in."""
    report = PurgeReport()
    stages: tuple[tuple[str, object], ...] = (
        ("documents", purge_expired_documents),
        ("cases", purge_expired_cases),
    )
    for name, stage in stages:
        try:
            stage_report = stage(db)
        except Exception:
            db.rollback()
            logger.exception("event=retention_stage_failed stage=%s", name)
            report.errors.append(f"stage {name} failed (see logs)")
            continue
        if name == "documents":
            report.documents_purged = stage_report.documents_purged
            report.documents_deferred = stage_report.documents_deferred
            report.skipped_active_jobs = stage_report.skipped_active_jobs
        else:
            report.cases_purged = stage_report.cases_purged
            report.cases_deferred = stage_report.cases_deferred
        report.errors.extend(stage_report.errors)
    try:
        report.sessions_purged = purge_expired_sessions(db)
    except Exception:
        db.rollback()
        logger.exception("event=retention_stage_failed stage=sessions")
        report.errors.append("stage sessions failed (see logs)")
    if report.documents_purged or report.cases_purged or report.sessions_purged:
        logger.info(
            "event=retention_sweep documents=%d cases=%d sessions=%d deferred=%d",
            report.documents_purged, report.cases_purged, report.sessions_purged,
            report.documents_deferred,
        )
    return report
