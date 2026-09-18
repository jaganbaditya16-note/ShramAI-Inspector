from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ShramAI Inspector API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": app.version}

@app.get("/api/v1/cases")
def list_cases():
    return {
        "items": [
            {
                "id": "DEMO-001",
                "name": "Demo Factory Inspection",
                "status": "needs_review",
                "documents": 3,
                "findings": 4,
            }
        ]
    }
