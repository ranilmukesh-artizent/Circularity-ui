"""One error shape for every refusal and failure di-api answers with (docs/agents/plans/01b-refactor.md, D1):

    {"ok": false, "error": {"code": "...", "message": "...", ...extra}}

the same shape POST /api/actions/{id} answers a refused action with. `register(app)` installs the handlers:

- `ApiError(code, message, status=400, extra=None)`: raise it from an endpoint;
- FastAPI's/Starlette's `HTTPException`: a detail {code, message, ...} is kept as it is; a plain string becomes the
  message, with a code from the status (404 not_found ...). Its headers (WWW-Authenticate) are kept;
- request validation errors: 422, code validation_error, the message names the first bad field;
- anything else: logged with its traceback, 500, code internal_error and a generic message (no detail leaks).
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("di.errors")

INTERNAL_MESSAGE = "Something went wrong on the server. Try again, or tell your administrator if it keeps happening."
_LOCATIONS = ("body", "query", "path", "header", "cookie")
_CODE_BY_STATUS = {
    400: "validation_error",
    401: "unauthenticated",
    403: "out_of_scope",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
}


class ApiError(Exception):
    """A refusal with a machine-readable code and a message for people, answered at `status`."""

    def __init__(self, code: str, message: str, status: int = 400, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra or {}


def envelope(code: str, message: str, extra: dict[str, Any] | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, **(extra or {})}}


def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(envelope(exc.code, exc.message, exc.extra), exc.status)


def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    d = exc.detail
    if isinstance(d, dict) and "code" in d and "message" in d:
        error = dict(d)
    else:
        code = _CODE_BY_STATUS.get(exc.status_code, "error")
        error = {"code": code, "message": d if isinstance(d, str) and d else HTTPStatus(exc.status_code).phrase}
    return JSONResponse({"ok": False, "error": error}, exc.status_code, headers=exc.headers)


def _field(loc: tuple | list) -> str:
    parts = [str(x) for x in loc]
    if len(parts) > 1 and parts[0] in _LOCATIONS:
        parts = parts[1:]
    return ".".join(parts) or "input"


def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if errors:
        first = errors[0]
        message = f"{_field(first.get('loc', ()))}: {first.get('msg', 'invalid value')}"
    else:
        message = "The input is not valid."
    return JSONResponse(envelope("validation_error", message), 422)


def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(envelope("internal_error", INTERNAL_MESSAGE), 500)


def register(app: FastAPI) -> None:
    # Starlette types a handler as taking any Exception; each of these is registered for its own exception class.
    app.add_exception_handler(ApiError, _api_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled)
