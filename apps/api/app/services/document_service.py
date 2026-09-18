"""Document services: validated persistence and authorised reads.

Security scanning order (fail-closed):
1. ``validate_upload`` — type/signature/size checks (unchanged).
2. ``scan_upload``     — malware scanning per configured mode.
   - clean / skipped → store + register, processing may proceed.
   - infected        → document row persisted as ``rejected`` (metadata +
     signature name only, bytes discarded), audit event, 400 to client.
   - unavailable / timeout / error / oversize → NOTHING is stored (fail
     closed), audit event, 503/413 to client.
"""

from __future__ import annotations

import contextlib
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import (
    InfectedDocument,
    NotFound,
    ScanFailed,
    ScanStreamLimit,
    ScanTimeout,
    ScanUnavailable,
    StorageUnavailable,
)
from ..core.security import Principal
from ..models import Case, Document, ProcessingJob
from . import audit_service
from .malware import ScanVerdict, scan_upload
from .storage import StorageError, get_store
from .validation import ValidatedUpload, validate_upload

logger = logging.getLogger("shramai.documents")

_BLOCKED_AUDIT_MAX_NOTE = 160


def _blocked_error(
    verdict: ScanVerdict,
) -> InfectedDocument | ScanUnavailable | ScanTimeout | ScanFailed | ScanStreamLimit:
    messages = {
        ScanVerdict.UNAVAILABLE: "Malware scanning is unavailable; the upload was not accepted.",
        ScanVerdict.TIMEOUT: "Malware scanning timed out; the upload was not accepted.",
        ScanVerdict.ERROR: "Malware scanning failed; the upload was not accepted.",
        ScanVerdict.OVERSIZE: "Upload exceeds the malware scanner's stream size limit.",
    }
    return {
        ScanVerdict.UNAVAILABLE: ScanUnavailable,
        ScanVerdict.TIMEOUT: ScanTimeout,
        ScanVerdict.ERROR: ScanFailed,
        ScanVerdict.OVERSIZE: ScanStreamLimit,
    }[verdict](messages[verdict])


async def persist_upload(
    db: Session,
    principal: Principal,
    case: Case,
    *,
    data: bytes,
    declared_content_type: str | None,
    raw_filename: str | None,
) -> tuple[Document, ProcessingJob]:
    """Validate → malware-scan → store + register an upload.

    The returned document/job always have a passing scan verdict; failing
    scans raise the mapped AppError after persisting the audit evidence."""
    validated: ValidatedUpload = validate_upload(data, declared_content_type, raw_filename)

    scan_result = await scan_upload(validated.data, validated.filename)
    scan_detail = {
        "filename": validated.filename,
        "sha256": validated.sha256[:16],
        "size_bytes": validated.size_bytes,
        "verdict": scan_result.verdict.value,
        "engine": scan_result.engine,
        "signature": scan_result.signature,
        "duration_ms": scan_result.duration_ms,
    }

    if scan_result.verdict == ScanVerdict.INFECTED:
        # Persist metadata-only evidence; the bytes are never written to storage.
        document = Document(
            org_id=principal.org_id,
            case_id=case.id,
            original_filename=validated.filename,
            storage_key="",  # intentionally empty: rejected content is not stored
            content_type=validated.content_type,
            size_bytes=validated.size_bytes,
            sha256=validated.sha256,
            status="rejected",
            scan_status=ScanVerdict.INFECTED.value,
            scan_engine=scan_result.engine,
            scan_signature=scan_result.signature,
            scan_note=(scan_result.note or "")[:200],
            created_by=principal.user_id,
        )
        db.add(document)
        db.flush()
        audit_service.record(
            db,
            action="document_scan_infected",
            org_id=principal.org_id,
            case_id=case.id,
            actor=principal,
            detail={**scan_detail, "document_id": document.id, "outcome": "rejected_not_stored"},
        )
        db.commit()
        raise InfectedDocument(
            "Upload rejected: the malware scanner identified this document as infected."
        )

    if scan_result.blocked:
        # Fail closed: no document bytes or rows are persisted for blocked scans.
        audit_service.record(
            db,
            action="document_scan_blocked",
            org_id=principal.org_id,
            case_id=case.id,
            actor=principal,
            detail={
                **scan_detail,
                "note": (scan_result.note or "")[:_BLOCKED_AUDIT_MAX_NOTE],
                "outcome": "upload_refused",
            },
        )
        db.commit()
        raise _blocked_error(scan_result.verdict)

    # Passing scan (clean or explicitly skipped): store and register as before.
    try:
        key = get_store().save(validated.data, validated.suffix)
    except StorageError as exc:
        logger.error(
            "event=document_storage_write_failed case=%s size=%d sha256=%s",
            case.id, validated.size_bytes, validated.sha256[:16],
        )
        raise StorageUnavailable(
            "The document could not be stored; the upload was not accepted."
        ) from exc
    try:
        document = Document(
            org_id=principal.org_id,
            case_id=case.id,
            original_filename=validated.filename,
            storage_key=key,
            content_type=validated.content_type,
            size_bytes=validated.size_bytes,
            sha256=validated.sha256,
            status="queued",
            scan_status=scan_result.verdict.value,
            scan_engine=scan_result.engine,
            scan_note=(scan_result.note or "")[:200] or None,
            created_by=principal.user_id,
        )
        db.add(document)
        db.flush()
        job = ProcessingJob(org_id=principal.org_id, document_id=document.id, status="queued")
        db.add(job)
        audit_service.record(
            db,
            action="document_uploaded",
            org_id=principal.org_id,
            case_id=case.id,
            actor=principal,
            detail={
                "document_id": document.id,
                "filename": validated.filename,
                "size_bytes": validated.size_bytes,
                "content_type": validated.content_type,
                "sha256": validated.sha256[:16],
            },
            commit=False,
        )
        audit_service.record(
            db,
            action=(
                "document_scan_clean" if scan_result.verdict == ScanVerdict.CLEAN
                else "document_scan_skipped"
            ),
            org_id=principal.org_id,
            case_id=case.id,
            actor=principal,
            detail={**scan_detail, "document_id": document.id},
            commit=False,
        )
        db.commit()
        db.refresh(document)
        db.refresh(job)
        return document, job
    except Exception:
        # The object must not outlive a failed registration (upload
        # interruption / commit failure): best-effort removal, then re-raise.
        with contextlib.suppress(Exception):
            get_store().delete(key)
        raise


def get_document_or_404(db: Session, principal: Principal, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.org_id != principal.org_id:
        raise NotFound("Document not found.")
    return document


def latest_job(db: Session, document_id: str) -> ProcessingJob | None:
    return latest_jobs_for_documents(db, [document_id]).get(document_id)


def latest_jobs_for_documents(db: Session, document_ids: list[str]) -> dict[str, ProcessingJob]:
    """Newest job per document in ONE query (avoids the per-row N+1 on list
    endpoints). Window functions are supported by SQLite 3.25+ and Postgres."""
    if not document_ids:
        return {}
    ranked = (
        select(
            ProcessingJob.id.label("job_id"),
            func.row_number()
            .over(
                partition_by=ProcessingJob.document_id,
                order_by=ProcessingJob.created_at.desc(),
            )
            .label("rn"),
        )
        .where(ProcessingJob.document_id.in_(document_ids))
        .subquery()
    )
    jobs = db.scalars(
        select(ProcessingJob)
        .join(ranked, ProcessingJob.id == ranked.c.job_id)
        .where(ranked.c.rn == 1)
    ).all()
    return {job.document_id: job for job in jobs}


def delete_document(db: Session, principal: Principal, document: Document) -> None:
    """Hard-delete a document: object first, then the row.

    If the storage backend fails, the row is kept (no dangling record pointing
    at an unremoved object); a missing object is treated as already deleted.
    """
    try:
        get_store().delete(document.storage_key)
    except StorageError as exc:
        raise StorageUnavailable(
            "The stored file could not be deleted; the document was kept."
        ) from exc
    db.delete(document)
    audit_service.record(
        db, action="document_deleted", org_id=principal.org_id, case_id=document.case_id,
        actor=principal,
        detail={"document_id": document.id, "filename": document.original_filename},
    )
