"""Lỗi nghiệp vụ và định dạng lỗi chung trả về client: {code, message, details} (NFR-07)."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class BusinessRuleError(AppError):
    """Vi phạm quy tắc nghiệp vụ (sai trạng thái, quá hạn, ...)."""

    status_code = 422
    code = "BUSINESS_RULE_VIOLATION"


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "details": details}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=jsonable_encoder(_error_body(exc.code, exc.message, exc.details)),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(_error_body("VALIDATION_ERROR", "Dữ liệu gửi lên không hợp lệ", exc.errors())),
        )
