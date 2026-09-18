"""Document processing pipeline orchestration.

States and guarantees:
- Document: queued -> processing -> processed | failed
- Job:      queued -> running -> succeeded | failed
- Every terminal state is persisted, so a restart can detect interrupted work
  (recovery runs at startup and marks stale jobs failed with a safe message).
- Extraction runs in a worker thread (bounded, CPU-heavy, never blocks the
  event loop). AI analysis is optional: unavailability never fails the job.
- Review decisions survive reprocessing: preserved by (rule_id, evidence_hash).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.errors import ExtractionFailure
from ..core.logging import get_logger
from ..db.helpers import utcnow
from ..db.session import SessionLocal
from ..models import Case, Document, Finding, ModelRun, ProcessingJob
from . import audit_service
from .ai import PROMPT_VERSION, analyze_document, approximate_page, ground_evidence
from .classification import classify
from .extraction import ExtractionResult, extract_document
from .rules import RULE_VERSION, RuleContext, evidence_hash, run_rules
from .rules.base import RuleViolation
from .storage import get_store

logger = get_logger(__name__)

_DOCUMENT_TERMINAL = {"processed", "failed"}
_JOB_TERMINAL = {"succeeded", "failed"}


def _page_map(result: ExtractionResult) -> list[dict[str, int]]:
    return [{"page": p.page, "start": p.start, "end": p.end} for p in result.pages]


def _preserve_decisions(existing: list[Finding]) -> dict[tuple[str, str], Finding]:
    """Map reviewed findings by (rule_id, evidence_hash) for decision carry-over."""
    preserved: dict[tuple[str, str], Finding] = {}
    for finding in existing:
        if finding.is_reviewed:
            preserved[(finding.rule_id, finding.evidence_hash)] = finding
    return preserved


def _insert_violation(
    db: Session,
    document: Document,
    violation: RuleViolation,
    *,
    origin: str,
    preserved: dict[tuple[str, str], Finding],
    ai_metadata: dict[str, Any] | None = None,
) -> Finding:
    key = (violation.rule_id, evidence_hash(violation.evidence_quote))
    previous = preserved.get(key)
    finding = Finding(
        org_id=document.org_id,
        case_id=document.case_id,
        document_id=document.id,
        rule_id=violation.rule_id,
        rule_version=RULE_VERSION,
        origin=origin,
        title=violation.title,
        severity=violation.severity,
        status=previous.status if previous else "needs_review",
        explanation=violation.explanation,
        evidence_kind=violation.evidence_kind,
        evidence_quote=violation.evidence_quote,
        evidence_hash=evidence_hash(violation.evidence_quote),
        page=violation.page,
        char_start=violation.char_start,
        char_end=violation.char_end,
        confidence=violation.confidence,
        metadata_json=ai_metadata,
        reviewed_by=previous.reviewed_by if previous else None,
        reviewed_at=previous.reviewed_at if previous else None,
        review_note=previous.review_note if previous else None,
    )
    db.add(finding)
    return finding


@dataclass
class PipelineOutcome:
    document_status: str
    rule_findings: int = 0
    ai_findings: int = 0
    ai_status: str = "disabled"
    ai_rejected: int = 0
    warnings: list[str] | None = None

    def job_detail(self) -> dict[str, Any]:
        return {
            "rule_findings": self.rule_findings,
            "ai_findings": self.ai_findings,
            "ai_status": self.ai_status,
            "ai_findings_rejected_ungrounded": self.ai_rejected,
            "warnings": self.warnings or [],
        }


async def run_pipeline(db: Session, document_id: str, job_id: str) -> PipelineOutcome:
    document = db.get(Document, document_id)
    job = db.get(ProcessingJob, job_id)
    if document is None or job is None:
        logger.error("event=pipeline_missing_entities document=%s job=%s", document_id, job_id)
        return PipelineOutcome(document_status="failed")

    job.status = "running"
    job.started_at = job.started_at or utcnow()
    job.attempts += 1
    document.status = "processing"
    document.error = None
    db.commit()

    timings: dict[str, int] = {}
    outcome = PipelineOutcome(document_status="processed")

    try:
        # 1. Extraction (thread: CPU-bound parsing/OCR).
        started = time.perf_counter()
        path = get_store().open_path(document.storage_key)
        try:
            extraction = await asyncio.to_thread(extract_document, path)
        except ExtractionFailure as exc:
            document.status = "failed"
            document.error = exc.message
            job.status = "failed"
            job.error = exc.message
            job.finished_at = utcnow()
            db.commit()
            audit_service.record(
                db, action="document_processing_failed", org_id=document.org_id,
                case_id=document.case_id,
                detail={"document_id": document.id, "reason": exc.message},
            )
            return PipelineOutcome(document_status="failed")
        timings["extraction_ms"] = int((time.perf_counter() - started) * 1000)

        document.extracted_text = extraction.text
        document.page_map = _page_map(extraction)
        document.page_count = extraction.page_count
        document.text_chars = len(extraction.text)
        document.extraction_method = extraction.method
        outcome.warnings = extraction.warnings
        db.commit()

        # 2. Classification.
        started = time.perf_counter()
        classification = classify(extraction.text)
        document.doc_type = classification.doc_type
        document.doc_type_confidence = classification.confidence
        db.commit()
        timings["classification_ms"] = int((time.perf_counter() - started) * 1000)

        # 3. Deterministic rules (decision-preserving replace).
        started = time.perf_counter()
        existing = list(
            db.scalars(select(Finding).where(Finding.document_id == document.id)).all()
        )
        preserved = _preserve_decisions(existing)
        db.execute(delete(Finding).where(Finding.document_id == document.id))
        ctx = RuleContext(
            text=extraction.text,
            normalized_text=" ".join(extraction.text.lower().split()),
            pages=extraction.pages,
            doc_type=classification.doc_type,
            doc_type_confidence=classification.confidence,
        )
        violations = run_rules(ctx)
        for violation in violations:
            _insert_violation(db, document, violation, origin="rule", preserved=preserved)
        outcome.rule_findings = len(violations)
        timings["rules_ms"] = int((time.perf_counter() - started) * 1000)

        # 4. Optional AI analysis (grounded; availability never fails the job).
        started = time.perf_counter()
        ai_result = await analyze_document(extraction.text, document.page_map)
        timings["ai_ms"] = int((time.perf_counter() - started) * 1000)
        outcome.ai_status = ai_result.status
        outcome.ai_rejected = ai_result.rejected_count
        db.add(
            ModelRun(
                org_id=document.org_id,
                document_id=document.id,
                provider=ai_result.provider,
                model=ai_result.model,
                status=ai_result.status,
                prompt_version=PROMPT_VERSION if ai_result.status != "disabled" else "",
                latency_ms=ai_result.latency_ms,
                findings_produced=len(ai_result.findings),
                findings_rejected=ai_result.rejected_count,
                error=ai_result.error,
            )
        )
        if ai_result.status == "succeeded":
            for ai_finding in ai_result.findings:
                _, grounded_offset = ground_evidence(ai_finding.evidence, extraction.text)
                violation = RuleViolation(
                    rule_id=ai_finding.rule_id,
                    title=ai_finding.title,
                    severity=ai_finding.severity,
                    explanation=ai_finding.explanation,
                    evidence_kind="quote",
                    evidence_quote=ai_finding.evidence,
                    page=approximate_page(grounded_offset, document.page_map),
                    char_start=grounded_offset,
                    char_end=(
                        grounded_offset + len(ai_finding.evidence)
                        if grounded_offset is not None
                        else None
                    ),
                    confidence=ai_finding.confidence,
                )
                _insert_violation(
                    db, document, violation, origin="ai", preserved=preserved,
                    ai_metadata={
                        "provider": ai_result.provider,
                        "model": ai_result.model,
                        "prompt_version": PROMPT_VERSION,
                        "grounding": "verified",
                    },
                )
            outcome.ai_findings = len(ai_result.findings)

        # 5. Terminal states.
        document.status = "processed"
        document.processed_at = utcnow()
        document.error = None
        case = db.get(Case, document.case_id)
        if case and case.status == "draft":
            case.status = "in_review"
        job.status = "succeeded"
        job.error = None
        job.detail = {**outcome.job_detail(), "timings_ms": timings}
        job.finished_at = utcnow()
        db.commit()
        audit_service.record(
            db, action="document_processed", org_id=document.org_id, case_id=document.case_id,
            detail={
                "document_id": document.id,
                "filename": document.original_filename,
                "doc_type": document.doc_type,
                "extraction_method": extraction.method,
                "rule_version": RULE_VERSION,
                "rule_findings": outcome.rule_findings,
                "ai_status": outcome.ai_status,
                "ai_findings": outcome.ai_findings,
            },
        )
        logger.info(
            "event=document_processed document=%s rules=%d ai=%s",
            document.id, outcome.rule_findings, outcome.ai_status,
        )
        return outcome

    except Exception:
        db.rollback()
        logger.exception("event=pipeline_failed document=%s", document_id)
        safe_message = "Processing failed unexpectedly. The document can be reprocessed."
        try:
            document.status = "failed"
            document.error = safe_message
            job.status = "failed"
            job.error = safe_message
            job.detail = {"timings_ms": timings}
            job.finished_at = utcnow()
            db.commit()
            audit_service.record(
                db, action="document_processing_failed", org_id=document.org_id,
                case_id=document.case_id,
                detail={"document_id": document.id, "reason": "unexpected_error"},
            )
        except Exception:
            logger.exception("event=pipeline_failure_persistence_failed document=%s", document_id)
        return PipelineOutcome(document_status="failed")




class PipelineScheduler:
    """In-process background scheduling with bounded concurrency."""

    def __init__(self, concurrency: int | None = None) -> None:
        self._semaphore = asyncio.Semaphore(concurrency or settings.pipeline_concurrency)
        self._tasks: set[asyncio.Task] = set()

    def schedule(self, document_id: str, job_id: str) -> None:
        task = asyncio.get_running_loop().create_task(self._run(document_id, job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, document_id: str, job_id: str) -> None:
        async with self._semaphore:
            db = SessionLocal()
            try:
                await run_pipeline(db, document_id, job_id)
            finally:
                db.close()

    async def drain(self) -> None:
        """Wait for scheduled tasks (used by tests)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


scheduler = PipelineScheduler()


def recover_interrupted_jobs(db: Session) -> int:
    """Mark jobs/documents interrupted by a restart as failed (safe message).

    Returns the number of recovered documents. In inline deployments the
    upload request itself performs processing, so nothing is ever stale.
    """
    stale_jobs = list(
        db.scalars(select(ProcessingJob).where(ProcessingJob.status.in_(("queued", "running"))))
    )
    recovered = 0
    for job in stale_jobs:
        job.status = "failed"
        job.error = "Processing was interrupted by a service restart. Reprocess the document."
        job.finished_at = utcnow()
        document = db.get(Document, job.document_id)
        if document and document.status not in _DOCUMENT_TERMINAL:
            document.status = "failed"
            document.error = job.error
            recovered += 1
    if stale_jobs:
        db.commit()
        logger.warning("event=interrupted_jobs_recovered count=%d", len(stale_jobs))
    return recovered
