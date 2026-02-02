import sys
import os
from pathlib import Path
from contextvars import ContextVar
from typing import Optional
from loguru import logger
from fastapi import Request
from framework.config import settings

# Store current request in contextvars for async context
_current_request: ContextVar[Optional[Request]] = ContextVar("current_request", default=None)

# Ensure log directory exists
LOG_DIR = Path(settings.LOG_DIR)
LOG_DIR.mkdir(exist_ok=True)

class LogConfig:
    """Global logging configuration using Loguru."""
    @classmethod
    def setup_logging(cls):
        logger.remove()

        logger.add(
            sys.stdout,
            enqueue=True,
            backtrace=True,
            diagnose=True,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<magenta>Trace:{extra[trace_id]}</magenta> - <level>{message}</level>"
            ),
            level="INFO",
        )

        logger.add(
            LOG_DIR / "app_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="30 days",
            compression="zip",
            enqueue=True,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | Trace:{extra[trace_id]} - {message}",
            level="DEBUG",
        )

        logger.add(
            LOG_DIR / "error_{time:YYYY-MM-DD}.log",
            level="ERROR",
            rotation="100 MB",
            enqueue=True,
        )

        logger.configure(extra={"trace_id": "system"})

    @classmethod
    def setup_worker_logging(cls, worker_id: str):
        """Configure logging for a worker; logs go to a separate file."""
        logger.remove()

        logger.add(
            sys.stdout,
            enqueue=True,
            backtrace=True,
            diagnose=True,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                f"<magenta>Worker-{worker_id}</magenta> | "
                "<level>{message}</level>"
            ),
            level="INFO",
        )

        logger.add(
            LOG_DIR / f"worker_{worker_id}_{{time:YYYY-MM-DD}}.log",
            rotation="00:00",
            retention="30 days",
            compression="zip",
            enqueue=True,
            format=f"{{time:YYYY-MM-DD HH:mm:ss.SSS}} | {{level: <8}} | {{name}}:{{function}}:{{line}} | Worker-{worker_id} | {{message}}",
            level="DEBUG",
        )

        logger.add(
            LOG_DIR / f"worker_{worker_id}_error_{{time:YYYY-MM-DD}}.log",
            level="ERROR",
            rotation="100 MB",
            enqueue=True,
        )

        logger.configure(extra={"trace_id": f"worker-{worker_id}"})

def get_logger(name: str = None, request: Optional[Request] = None):
    """Get logger instance; optionally pass request for trace_id, else from context."""
    current_request = request or _current_request.get()
    
    if current_request is not None:
        trace_id = getattr(current_request.state, "trace_id", "unknown")
    else:
        trace_id = "unknown"
    
    if name:
        return logger.bind(name=name, trace_id=trace_id)
    else:
        return logger.bind(trace_id=trace_id)