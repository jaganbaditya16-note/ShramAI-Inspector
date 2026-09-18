from pathlib import Path
from uuid import uuid4
from fastapi import UploadFile, HTTPException
from ..core.config import settings

ALLOWED = {"application/pdf", "image/png", "image/jpeg"}
EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

async def save_upload(file: UploadFile) -> tuple[str, int]:
    suffix = Path(file.filename or "").suffix.lower()
    if file.content_type not in ALLOWED or suffix not in EXTENSIONS:
        raise HTTPException(400, "Unsupported document type. Use PDF, PNG or JPEG.")
    data = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit.")
    directory = Path(settings.upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}{suffix}"
    path.write_bytes(data)
    return str(path), len(data)
