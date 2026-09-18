from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import CaseCreate, CaseList, CaseOut, HealthResponse

app = FastAPI(title="ShramAI Inspector API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

_demo_cases = [
    CaseOut(
        id="DEMO-001",
        name="Demo Factory Inspection",
        status="needs_review",
        documents=3,
        findings=4,
    )
]

@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=app.version)

@app.get("/api/v1/cases", response_model=CaseList)
def list_cases() -> CaseList:
    return CaseList(items=_demo_cases)

@app.post("/api/v1/cases", response_model=CaseOut, status_code=201)
def create_case(payload: CaseCreate) -> CaseOut:
    case_id = f"DEMO-{len(_demo_cases) + 1:03d}"
    case = CaseOut(id=case_id, name=payload.name, status="draft", documents=0, findings=0)
    _demo_cases.append(case)
    return case

@app.get("/api/v1/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: str) -> CaseOut:
    for case in _demo_cases:
        if case.id == case_id:
            return case
    raise HTTPException(status_code=404, detail="Case not found")
