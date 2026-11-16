"""Stable, privacy-safe HTTP error contract for the Web trial.

Keep the legacy 'detail' key for existing UI consumers. Never place source
documents, invalid request values, stack traces, or client-supplied IDs in
machine-readable error metadata.
"""
from fastapi.responses import JSONResponse

ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    408: "REQUEST_TIMEOUT",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "INVALID_REQUEST",
    429: "RATE_LIMITED",
    499: "CLIENT_DISCONNECTED",
    503: "SERVICE_UNAVAILABLE",
}


def error_code(status: int) -> str:
    return ERROR_CODES.get(status, "SERVER_ERROR" if status >= 500 else "HTTP_ERROR")


def error_response(status: int, detail: str, request_id: str | None) -> JSONResponse:
    return JSONResponse(
        {"detail": detail,
         "error": {"code": error_code(status), "requestId": request_id}},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


def safe_error_response(request, status: int, detail: str) -> JSONResponse:
    return error_response(status, detail, getattr(request.state, "request_id", None))
