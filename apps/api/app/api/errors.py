"""HTTP error envelopes preserve legacy detail while exposing stable codes and correlation."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from qa_core.failure.redactor import SensitiveRedactor
from starlette.exceptions import HTTPException


def error_response(request: Request, status: int, detail, *, code: str | None = None):
    safe = SensitiveRedactor.redact_value(detail)
    body = safe if isinstance(safe, dict) else {}
    message = body.get("message") or (safe if isinstance(safe, str) else "Request validation failed.")
    return JSONResponse(
        status_code=status,
        content={
            "detail": safe,
            "code": body.get("code") or code or f"HTTP_{status}",
            "message": message,
            "details": body.get("details", {}),
            "request_id": getattr(request.state, "request_id", None),
        },
    )


async def http_error(request: Request, error: HTTPException):
    response = error_response(request, error.status_code, error.detail)
    if error.headers:
        response.headers.update(error.headers)
    return response


async def validation_error(request: Request, error: RequestValidationError):
    # Validation input may contain an API key: report fields/reasons, never submitted values.
    issues = [{"type": item["type"], "loc": list(item["loc"]), "msg": item["msg"]} for item in error.errors()]
    return error_response(request, 422, issues, code="VALIDATION_ERROR")
