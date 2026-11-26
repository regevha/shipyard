"""Shared error envelope for every Shipyard service (T022, Q-21).

Canonical file: shared/errors.py. Each service holds a byte-identical copy at app/errors.py
(scripts/ci/check_shared_copy.py enforces it). Never edit a copy.

Usage: ``install(app)`` once, after creating the FastAPI app. Raise
``ApiError(404, "not_found", msg)`` for expected errors; everything else is turned into the envelope
of contracts/errors.yml.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from typing import Any, Literal, get_args

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

ErrorCode = Literal[
    "validation_failed",
    "not_found",
    "method_not_allowed",
    "release_already_decided",
    "release_not_approved",
    "checksum_mismatch",
    "payload_too_large",
    "internal_error",
]

# The (status, code) pairs of contracts/errors.yml x-status-codes; a test keeps them equal.
ALLOWED_PAIRS: frozenset[tuple[int, str]] = frozenset(
    {
        (404, "not_found"),
        (405, "method_not_allowed"),
        (409, "release_already_decided"),
        (409, "release_not_approved"),
        (413, "payload_too_large"),
        (422, "validation_failed"),
        (422, "checksum_mismatch"),
        (500, "internal_error"),
    }
)

MAX_DETAILS = 100


class ErrorDetail(BaseModel):
    """One problem found in the request (location is dot-separated, e.g. body.steps.0.name)."""

    model_config = ConfigDict(extra="forbid")

    location: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str = Field(min_length=1)
    details: list[ErrorDetail] | None = Field(default=None, min_length=1)


class ErrorEnvelope(BaseModel):
    """The only error body any service returns."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class ApiError(Exception):
    """An expected error; the handler answers it with the envelope as given."""

    def __init__(
        self,
        status: int,
        code: ErrorCode,
        message: str,
        details: Sequence[ErrorDetail] | None = None,
    ) -> None:
        if (status, code) not in ALLOWED_PAIRS:
            raise ValueError(f"({status}, {code!r}) is not a status/code pair of errors.yml")
        if not message:
            raise ValueError("message must not be empty")
        super().__init__(message)
        self.status = status
        self.code: ErrorCode = code
        self.message = message
        self.details = list(details) if details else None


def _envelope(
    status: int,
    code: ErrorCode,
    message: str,
    details: Sequence[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorBody(code=code, message=message, details=list(details) if details else None)
    )
    return JSONResponse(
        status_code=status, content=body.model_dump(mode="json", exclude_none=True), headers=headers
    )


def _location(loc: Sequence[Any]) -> str:
    return ".".join(str(part) for part in loc) or "body"


def _validation_details(exc: RequestValidationError) -> list[ErrorDetail]:
    details: list[ErrorDetail] = []
    for err in exc.errors()[:MAX_DETAILS]:
        if err.get("type") == "json_invalid":
            details.append(ErrorDetail(location="body", message="request body is not valid JSON"))
            continue
        details.append(
            ErrorDetail(
                location=_location(err.get("loc", ())),
                message=str(err.get("msg") or "invalid value"),
            )
        )
    return details


async def _handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return _envelope(exc.status, exc.code, exc.message, exc.details)


async def _handle_validation(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return _envelope(
        422, "validation_failed", "request validation failed", _validation_details(exc)
    )


async def _handle_http(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    headers = dict(exc.headers) if exc.headers else None
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else None
    status = exc.status_code
    if status >= 500:
        return _envelope(500, "internal_error", "internal server error", headers=headers)
    if status == 404:
        return _envelope(404, "not_found", detail or "not found", headers=headers)
    if status == 405:
        return _envelope(405, "method_not_allowed", detail or "method not allowed", headers=headers)
    if status == 413:
        return _envelope(413, "payload_too_large", detail or "payload too large", headers=headers)
    return _envelope(
        422, "validation_failed", detail or "request validation failed", headers=headers
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # No internals in the body; the server log (uvicorn) shows the re-raised exception.
    return _envelope(500, "internal_error", "internal server error")


_ENVELOPE_REF = {"$ref": "#/components/schemas/ErrorEnvelope"}


def _component_schemas() -> dict[str, Any]:
    return {
        "ErrorCode": {"type": "string", "enum": list(get_args(ErrorCode))},
        "ErrorDetail": {
            "type": "object",
            "additionalProperties": False,
            "required": ["location", "message"],
            "properties": {
                "location": {"type": "string", "minLength": 1},
                "message": {"type": "string", "minLength": 1},
            },
        },
        "ErrorEnvelope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["code", "message"],
                    "properties": {
                        "code": {"$ref": "#/components/schemas/ErrorCode"},
                        "message": {"type": "string", "minLength": 1},
                        "details": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"$ref": "#/components/schemas/ErrorDetail"},
                        },
                    },
                }
            },
        },
    }


def _is_error_status(key: str) -> bool:
    return key[:1] in ("4", "5") and (key.isdigit() or key[1:].upper() == "XX")


def _envelope_response(description: str) -> dict[str, Any]:
    return {"description": description, "content": {"application/json": {"schema": _ENVELOPE_REF}}}


_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _transform(spec: dict[str, Any]) -> dict[str, Any]:
    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    schemas.pop("HTTPValidationError", None)
    schemas.pop("ValidationError", None)
    schemas.update(_component_schemas())
    for item in spec.get("paths", {}).values():
        for method, op in item.items():
            if method not in _METHODS:
                continue
            responses = op.setdefault("responses", {})
            responses.setdefault("422", {"description": "Validation failed"})
            responses.setdefault("500", {"description": "Internal server error"})
            for key, resp in list(responses.items()):
                if _is_error_status(str(key)):
                    description = resp.get("description") or "Error"
                    responses[key] = _envelope_response(description)
    return spec


def install(app: FastAPI) -> None:
    """Register the envelope handlers and replace the generated OpenAPI."""
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http)
    app.add_exception_handler(Exception, _handle_unexpected)

    original: Callable[[], dict[str, Any]] = app.openapi
    cache: dict[str, Any] = {}

    def openapi() -> dict[str, Any]:
        if not cache:
            cache.update(_transform(copy.deepcopy(original())))
        app.openapi_schema = cache
        return cache

    app.openapi = openapi  # type: ignore[method-assign]
