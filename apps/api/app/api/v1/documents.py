"""Document endpoints: upload (202 + background processing), status polling,
authorised download and reprocessing."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.errors import Conflict, NotFound, StorageUnavailable
from ...core.security import Principal
from ...db.session import get_db
from ...models import Document, ProcessingJob
from ...schemas import DocumentList, DocumentOut, JobOut, UploadAccepted
from ...services import audit_service, case_service, document_service, pipeline
from ...services.pipeline import scheduler
from ...services.storage import MissingObjectError, StorageError
from ...services.validation import read_bounded_upload
from ..deps import PageParams, get_principal, rate_limit_upload, require_inspector

router = APIRouter(tags=["documents"])


def _job_out(job: ProcessingJob | None) -> JobOut | None:
    if job is None:
        return None
    return JobOut(
        id=job.id, status=job.status, error=job.error, detail=job.detail,
        created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
    )


def _document_out(document: Document, job: ProcessingJob | None) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        case_id=document.case_id,
        original_filename=document.original_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        status=document.status,
        error=document.error,
        page_count=document.page_count,
        text_chars=document.text_chars,
        extraction_method=document.extraction_method,
        doc_type=document.doc_type,
        doc_type_confidence=document.doc_type_confidence,
        created_at=document.created_at,
        processed_at=document.processed_at,
        scan_status=document.scan_status,
        scan_signature=document.scan_signature,
        scan_note=document.scan_note,
        job=_job_out(job),
    )


@router.post("/cases/{case_id}/documents", status_code=202,
             response_model=UploadAccepted, dependencies=[Depends(rate_limit_upload)])
async def upload_document(
    case_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_inspector),
    file: UploadFile = File(...),
) -> UploadAccepted:
    case = case_service.get_case_or_404(db, principal, case_id)
    if case.status == "closed":
        raise Conflict("Reopen the case before uploading documents.")
    data = await read_bounded_upload(file)
    document, job = await document_service.persist_upload(
        db, principal, case,
        data=data,
        declared_content_type=file.content_type,
        raw_filename=file.filename,
    )
    if settings.pipeline_mode == "inline":
        await pipeline.run_pipeline(db, document.id, job.id)
        db.refresh(document)
        db.refresh(job)
    else:
        scheduler.schedule(document.id, job.id)
    return UploadAccepted(
        document=_document_out(document, job),
        job=_job_out(job),
        message=(
            "Document processed." if settings.pipeline_mode == "inline"
            else "Document accepted and queued for processing."
        ),
    )


@router.get("/cases/{case_id}/documents", response_model=DocumentList)
def list_documents(
    case_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    page: PageParams = Depends(PageParams.depends),
) -> DocumentList:
    case_service.get_case_or_404(db, principal, case_id)
    conditions = [Document.case_id == case_id, Document.org_id == principal.org_id]
    total = db.scalar(select(func.count(Document.id)).where(*conditions)) or 0
    documents = db.scalars(
        select(Document).where(*conditions)
        .order_by(Document.created_at.desc()).limit(page.limit).offset(page.offset)
    ).all()
    return DocumentList(
        items=[_document_out(d, document_service.latest_job(db, d.id)) for d in documents],
        meta={"total": total, "limit": page.limit, "offset": page.offset},
    )


@router.get("/documents/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db),
                 principal: Principal = Depends(get_principal)) -> DocumentOut:
    document = document_service.get_document_or_404(db, principal, document_id)
    return _document_out(document, document_service.latest_job(db, document.id))


@router.post("/documents/{document_id}/reprocess", status_code=202, response_model=UploadAccepted)
async def reprocess_document(document_id: str, db: Session = Depends(get_db),
                             principal: Principal = Depends(require_inspector)) -> UploadAccepted:
    document = document_service.get_document_or_404(db, principal, document_id)
    active = db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.document_id == document.id,
            ProcessingJob.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise Conflict("A processing job is already running for this document.")
    if document.scan_status not in {"clean", "skipped"}:
        raise Conflict(
            "This document cannot be processed because its security scan did not pass."
        )
    job = ProcessingJob(org_id=principal.org_id, document_id=document.id, status="queued")
    db.add(job)
    document.status = "queued"
    document.error = None
    db.commit()
    db.refresh(job)
    audit_service.record(
        db, action="document_reprocess_requested", org_id=principal.org_id,
        case_id=document.case_id, actor=principal,
        detail={"document_id": document.id},
    )
    if settings.pipeline_mode == "inline":
        await pipeline.run_pipeline(db, document.id, job.id)
        db.refresh(document)
        db.refresh(job)
    else:
        scheduler.schedule(document.id, job.id)
    return UploadAccepted(
        document=_document_out(document, job), job=_job_out(job),
        message="Reprocessing started.",
    )


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, db: Session = Depends(get_db),
                    principal: Principal = Depends(require_inspector)) -> Response:
    """Org-scoped hard delete of one document.

    Delegates to the retention service: the storage object is removed first
    (a backend failure keeps the row so deletion can be retried — no orphaned
    objects, no dangling rows), then the row with its extracted text,
    findings, model runs and processing jobs. Audit events are preserved."""
    document = document_service.get_document_or_404(db, principal, document_id)
    document_service.delete_document(db, principal, document)
    return Response(status_code=204)


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db),
                      principal: Principal = Depends(get_principal)) -> Response:
    """Authorised streaming of the stored original. Storage keys are server
    generated and access is re-checked on every request (no unsigned URLs).

    Objects stay private on every backend: the default path streams bytes
    through this authorised endpoint; presigned URLs are used only when the
    operator explicitly enables them, and they are short-lived."""
    document = document_service.get_document_or_404(db, principal, document_id)
    if not document.storage_key or document.status == "rejected":
        raise NotFound("No stored file exists for this document (security-scan rejected).")
    store = document_service.get_store()
    key = document.storage_key

    if settings.s3_presigned_downloads:
        url = store.presign_get(key, settings.s3_presign_ttl_seconds)
        if url is not None:
            return RedirectResponse(url, status_code=307, headers={"Cache-Control": "no-store"})

    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": _content_disposition(document.original_filename),
    }
    if store.ephemeral_paths:
        # Backend without a filesystem (S3): stream through the authorised API.
        try:
            data = store.get_bytes(key)
        except MissingObjectError as exc:
            raise NotFound("Stored file is missing; the document may need re-upload.") from exc
        except StorageError as exc:
            raise StorageUnavailable(
                "The stored file is temporarily unavailable; try again."
            ) from exc
        return Response(content=data, media_type=document.content_type, headers=headers)

    path = store.open_path(key)
    if not path.is_file():
        raise NotFound("Stored file is missing; the document may need re-upload.")
    return FileResponse(
        path=path,
        media_type=document.content_type,
        headers=headers,  # includes the sanitised RFC-5987 Content-Disposition
    )


def _content_disposition(filename: str) -> str:
    """RFC 5987 attachment header; never contains storage keys."""
    fallback = filename.replace('"', "_").replace("\\", "_").encode("ascii", "ignore").decode()
    return (
        f"attachment; filename=\"{fallback or 'document'}\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )
