from pydantic import BaseModel, ConfigDict, Field

class HealthResponse(BaseModel):
    status: str
    version: str

class CaseCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    establishment_reference: str | None = Field(default=None, max_length=120)

class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    status: str
    documents: int
    findings: int

class CaseList(BaseModel):
    items: list[CaseOut]

class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    rule_id: str
    title: str
    severity: str
    status: str
    explanation: str
    evidence: str
    confidence: int = Field(ge=0, le=100)

class FindingUpdate(BaseModel):
    status: str = Field(pattern="^(accepted|rejected|needs_review)$")
