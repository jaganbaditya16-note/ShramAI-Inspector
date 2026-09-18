"""Application error types and a consistent, safe error envelope.

Every client-visible failure is an ``AppError`` carrying a stable machine code,
a safe human message and an HTTP status. Unexpected exceptions never reach the
client with stack traces; handlers convert them to a generic 500 envelope.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for expected, client-visible application errors."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None,
                 details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}


class ValidationFailure(AppError):
    status_code = 422
    code = "validation_failed"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class PayloadTooLarge(AppError):
    status_code = 413
    code = "payload_too_large"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


class UploadRejected(AppError):
    status_code = 400
    code = "upload_rejected"


class ExtractionFailure(AppError):
    status_code = 422
    code = "extraction_failed"


def error_envelope(code: str, message: str, request_id: str,
                   details: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {"code": code, "message": message, "request_id": request_id}
    }
    if details:
        body["error"]["details"] = details
    return body
