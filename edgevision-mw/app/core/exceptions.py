import traceback

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger("edgevision.exceptions")


class AppError(Exception):
    """Base application error."""

    def __init__(
        self,
        detail: str,
        status_code: int = 500,
        resource: str | None = None,
        trace_id: str | None = None,
        detail_dict: dict | None = None,
    ):
        self.detail = detail
        self.status_code = status_code
        self.resource = resource
        self.trace_id = trace_id
        self.detail_dict = detail_dict or {}


class NotFoundError(AppError):
    def __init__(self, detail: str = "Resource not found", resource: str | None = None, trace_id: str | None = None):
        super().__init__(detail=detail, status_code=status.HTTP_404_NOT_FOUND, resource=resource, trace_id=trace_id)


class ConflictError(AppError):
    def __init__(self, detail: str = "Resource conflict", resource: str | None = None, trace_id: str | None = None):
        super().__init__(detail=detail, status_code=status.HTTP_409_CONFLICT, resource=resource, trace_id=trace_id)


class PermissionDeniedError(AppError):
    def __init__(self, detail: str = "Insufficient permissions", trace_id: str | None = None):
        super().__init__(detail=detail, status_code=status.HTTP_403_FORBIDDEN, trace_id=trace_id)


class AuthenticationError(AppError):
    def __init__(self, detail: str = "Authentication required", trace_id: str | None = None):
        super().__init__(detail=detail, status_code=status.HTTP_401_UNAUTHORIZED, trace_id=trace_id)


class StorageError(AppError):
    """MinIO or filesystem operation failed."""

    def __init__(
        self,
        detail: str = "Storage operation failed",
        resource: str | None = None,
        trace_id: str | None = None,
        detail_dict: dict | None = None,
    ):
        super().__init__(detail=detail, status_code=500, resource=resource, trace_id=trace_id, detail_dict=detail_dict)


class DatabaseError(AppError):
    """Database operation failed (connection, constraint, etc.)."""

    def __init__(
        self,
        detail: str = "Database operation failed",
        resource: str | None = None,
        trace_id: str | None = None,
        detail_dict: dict | None = None,
    ):
        super().__init__(detail=detail, status_code=500, resource=resource, trace_id=trace_id, detail_dict=detail_dict)


class InferenceError(AppError):
    """Model inference or auto-labeling failed."""

    def __init__(
        self,
        detail: str = "Inference failed",
        resource: str | None = None,
        trace_id: str | None = None,
        detail_dict: dict | None = None,
    ):
        super().__init__(detail=detail, status_code=500, resource=resource, trace_id=trace_id, detail_dict=detail_dict)


class ValidationError(AppError):
    """Business logic validation failed (not request schema validation)."""

    def __init__(
        self,
        detail: str = "Validation failed",
        resource: str | None = None,
        trace_id: str | None = None,
        detail_dict: dict | None = None,
    ):
        super().__init__(detail=detail, status_code=422, resource=resource, trace_id=trace_id, detail_dict=detail_dict)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = []
        for error in exc.errors():
            loc = " -> ".join(str(part) for part in error.get("loc", []))
            errors.append({"field": loc, "message": error.get("msg", "")})
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "Validation error", "errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        extra = {"path": request.url.path, "method": request.method}
        if exc.trace_id:
            extra["trace_id"] = exc.trace_id
        if exc.resource:
            extra["resource"] = exc.resource
        exc_name = exc.__class__.__name__
        if exc.status_code >= 500:
            logger.error(f"platform_error_{exc_name}", **extra, error=str(exc), detail=exc.detail_dict)
        else:
            logger.warning(f"platform_{exc_name}", **extra, error=str(exc))
        content = {"detail": exc.detail}
        if exc.resource:
            content["resource"] = exc.resource
        if exc.trace_id:
            content["trace_id"] = exc.trace_id
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        user_id = getattr(request.state, "user_id", None)
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            user_id=user_id,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )
