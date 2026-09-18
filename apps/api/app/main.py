from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .core.config import settings
from .db import Base, engine, get_db
from .models import Case, Document, Finding
from .schemas import CaseCreate, CaseList, CaseOut, FindingOut, FindingUpdate, HealthResponse
from .security import require_demo_token
from .services.audit import record
from .services.documents import save_upload
from .services.extraction import extract_text
from .services.rules import RULE_VERSION, run_rules

Base.metadata.create_all(bind=engine)

app = FastAPI(title="ShramAI Inspector API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.allowed_origins.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > settings.max_request_body_mb * 1024 * 1024:
                return JSONResponse(status_code=413, content={"detail": "Request body exceeds configured limit."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if settings.app_env != "development":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

def case_out(case: Case) -> CaseOut:
    return CaseOut(
        id=case.id,
        name=case.name,
        status=case.status,
        documents=len(case.documents),
        findings=len(case.findings),
    )

@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=app.version)

@app.get("/api/v1/cases", response_model=CaseList, dependencies=[Depends(require_demo_token)])
def list_cases(db: Session = Depends(get_db)) -> CaseList:
    cases = db.scalars(select(Case).order_by(Case.created_at.desc())).all()
    if not cases:
        demo = Case(id="DEMO-001", name="Demo Factory Inspection", status="draft", establishment_reference="SYNTHETIC")
        db.add(demo)
        db.commit()
        db.refresh(demo)
        record(db, "demo_case_initialized", demo.id, {"synthetic": True})
        cases = [demo]
    return CaseList(items=[case_out(c) for c in cases])

@app.post("/api/v1/cases", response_model=CaseOut, status_code=201, dependencies=[Depends(require_demo_token)])
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> CaseOut:
    case = Case(id=f"CASE-{uuid4().hex[:12].upper()}", name=payload.name.strip(), establishment_reference=payload.establishment_reference)
    db.add(case)
    db.commit()
    db.refresh(case)
    record(db, "case_created", case.id, {"name": case.name})
    return case_out(case)

@app.get("/api/v1/cases/{case_id}", response_model=CaseOut, dependencies=[Depends(require_demo_token)])
def get_case(case_id: str, db: Session = Depends(get_db)) -> CaseOut:
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case_out(case)

@app.post("/api/v1/cases/{case_id}/documents", dependencies=[Depends(require_demo_token)])
async def upload_document(case_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    path, size = await save_upload(file)
    document = Document(
        id=f"DOC-{uuid4().hex[:12].upper()}",
        case_id=case_id,
        filename=Path(file.filename or "document").name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        path=path,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    record(db, "document_uploaded", case_id, {"document_id": document.id, "filename": document.filename, "size": size})
    return {"id": document.id, "filename": document.filename, "status": document.status}

@app.post("/api/v1/documents/{document_id}/process", dependencies=[Depends(require_demo_token)])
def process_document(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Document not found")
    db.execute(delete(Finding).where(Finding.document_id == document.id))
    text = extract_text(document.path)
    document.extracted_text = text
    document.status = "processed" if text.strip() else "needs_ocr_or_manual_review"
    results = run_rules(text)
    for item in results:
        db.add(Finding(
            id=f"FND-{uuid4().hex[:12].upper()}",
            case_id=document.case_id,
            document_id=document.id,
            rule_id=f"{item.rule_id}@{RULE_VERSION}",
            title=item.title,
            severity=item.severity,
            status="needs_review",
            explanation=item.explanation,
            evidence=f"{document.filename}: {item.evidence}",
            confidence=item.confidence,
        ))
    case = db.get(Case, document.case_id)
    if case:
        case.status = "needs_review"
    db.commit()
    record(db, "document_processed", document.case_id, {"document_id": document.id, "text_extracted": bool(text.strip()), "rule_version": RULE_VERSION})
    return {"document_id": document.id, "status": document.status, "characters_extracted": len(text), "findings_created": len(results)}

@app.get("/api/v1/cases/{case_id}/findings", response_model=list[FindingOut], dependencies=[Depends(require_demo_token)])
def list_findings(case_id: str, db: Session = Depends(get_db)):
    if not db.get(Case, case_id):
        raise HTTPException(404, "Case not found")
    return db.scalars(select(Finding).where(Finding.case_id == case_id).order_by(Finding.created_at.desc())).all()

@app.patch("/api/v1/findings/{finding_id}", response_model=FindingOut, dependencies=[Depends(require_demo_token)])
def update_finding(finding_id: str, payload: FindingUpdate, db: Session = Depends(get_db)):
    finding = db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(404, "Finding not found")
    finding.status = payload.status
    db.commit()
    record(db, "finding_reviewed", finding.case_id, {"finding_id": finding.id, "status": finding.status})
    return finding

@app.post("/api/v1/cases/{case_id}/report", dependencies=[Depends(require_demo_token)])
def generate_report(case_id: str, db: Session = Depends(get_db)):
    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    findings = db.scalars(select(Finding).where(Finding.case_id == case_id)).all()
    unresolved = sum(1 for f in findings if f.status == "needs_review")
    return {
        "case_id": case.id,
        "case_name": case.name,
        "rule_version": RULE_VERSION,
        "finding_count": len(findings),
        "unresolved_findings": unresolved,
        "disclaimer": "AI-assisted screening output. Final compliance determination remains with the authorized human reviewer.",
        "findings": [
            {"id": f.id, "rule_id": f.rule_id, "title": f.title, "severity": f.severity, "status": f.status, "confidence": f.confidence, "evidence": f.evidence, "explanation": f.explanation}
            for f in findings
        ],
    }
