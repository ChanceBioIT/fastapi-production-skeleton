from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from framework.logging.logger import get_logger
from framework.response import ResponseModel
from typing import Any
from framework.config import settings

logger = get_logger("exception_handler")

class BusinessException(Exception):
    """Base class for business exceptions."""
    def __init__(self, message: str, status_code: int = 200, code: int = 400, detail: Any = None):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.detail = detail

def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    trace_id = getattr(request.state, "trace_id", "unknown")
    
    if isinstance(exc, BusinessException):
        logger.warning(f"Trace[{trace_id}] - BusinessError: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content=ResponseModel.fail(code=exc.code, message=exc.message)
        )

    if isinstance(exc, RequestValidationError):
        logger.error(f"Trace[{trace_id}] - ValidationError: {exc.errors()}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ResponseModel.fail(code=422, message="Invalid request parameters", data=exc.errors())
        )

    if isinstance(exc, SQLAlchemyError):
        logger.critical(f"Trace[{trace_id}] - DatabaseError: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ResponseModel.fail(code=500, message="Service temporarily unavailable")
        )

    logger.opt(exception=True).error(f"Trace[{trace_id}] - UncaughtException: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ResponseModel.fail(
            code=500, 
            message="System busy, please try again later",
            data={"trace_id": trace_id} if settings.DEBUG else None
        )
    )