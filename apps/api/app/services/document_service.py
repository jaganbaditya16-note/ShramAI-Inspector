"""Document services: validated persistence and authorised reads."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import NotFound
from ..core.security import Principal
from ..models import Case, Document, ProcessingJob
from . import audit_service
from .storage import get_store
from .validation import ValidatedUpload, validate_upload


def persist_upload(
    db: Session,
    principal: Principal,
    case: Case,
    *,
    data: bytes,
    declared_content_type: str | None,
    raw_filename: str | None,
) -> tuple[Document, ProcessingJob]:
    """Validate + store + register an upload. Audit event is part of the same
    transaction so a stored file without a record can never exist."""
    validated: ValidatedUpload = validate_upload(data, declared_content_type, raw_filename)
    key = get_store().save(validated.data, validated.suffix)
    document = Document(
        org_id=principal.org_id,
        case_id=case.id,
        original_filename=validated.filename,
        storage_key=key,
        content_type=validated.content_type,
        size_bytes=validated.size_bytes,
        sha256=validated.sha256,
        status="queued",
        created_by=principal.user_id,
    )
    db.add(document)
    db.flush()
    job = ProcessingJob(org_id=principal.org_id, document_id=document.id, status="queued")
    db.add(job)
    audit_service.record(
        db, action="document_uploaded", org_id=principal.org_id, case_id=case.id,
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
    db.commit()
    db.refresh(document)
    db.refresh(job)
    return document, job


def get_document_or_404(db: Session, principal: Principal, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.org_id != principal.org_id:
        raise NotFound("Document not found.")
    return document


def latest_job(db: Session, document_id: str) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )


def delete_document(db: Session, principal: Principal, document: Document) -> None:
    get_store().delete(document.storage_key)
    db.delete(document)
    audit_service.record(
        db, action="document_deleted", org_id=principal.org_id, case_id=document.case_id,
        actor=principal,
        detail={"document_id": document.id, "filename": document.original_filename},
    )
