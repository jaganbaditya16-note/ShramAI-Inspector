import json

from ..models import AuditEvent


def record(db, action: str, case_id: str | None = None, detail: dict | None = None):
    db.add(AuditEvent(case_id=case_id, action=action, detail=json.dumps(detail or {}, ensure_ascii=False)))
    db.commit()
