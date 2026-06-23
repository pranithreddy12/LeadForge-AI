from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.logging import get_logger

log = get_logger(__name__)


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, **extra):
        super().__init__(status_code=status_code, detail={"code": code, "message": message, **extra})


class NotFound(AppError):
    def __init__(self, resource: str):
        super().__init__(status.HTTP_404_NOT_FOUND, "not_found", f"{resource} not found")


class Forbidden(AppError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(status.HTTP_403_FORBIDDEN, "forbidden", message)


class Conflict(AppError):
    def __init__(self, message: str):
        super().__init__(status.HTTP_409_CONFLICT, "conflict", message)


class RateLimited(AppError):
    def __init__(self, retry_after: int):
        super().__init__(429, "rate_limited", "Too many requests", retry_after=retry_after)


class AIUnavailable(AppError):
    def __init__(self, detail: str = "AI provider temporarily unavailable (rate-limited). Try again shortly."):
        super().__init__(503, "ai_unavailable", detail)


def register_error_handlers(app) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"code": "validation_error", "errors": exc.errors()},
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        log.warning("integrity_error", error=str(exc.orig))
        return JSONResponse(
            status_code=409,
            content={"code": "conflict", "message": "Resource already exists"},
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db(request: Request, exc: SQLAlchemyError):
        log.exception("db_error")
        return JSONResponse(
            status_code=500, content={"code": "db_error", "message": "Database error"}
        )
