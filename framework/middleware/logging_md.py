import uuid
import time
from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from framework.response import ResponseModel
from framework.logging.logger import _current_request

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        request.state.trace_id = trace_id
        token = _current_request.set(request)
        
        with logger.contextualize(trace_id=trace_id):
            start_time = time.time()
            
            logger.info(
                f"Request Started | Method: {request.method} | Path: {request.url.path} | "
                f"Client: {request.client.host if request.client else 'unknown'}"
            )

            try:
                response = await call_next(request)
                process_time = (time.time() - start_time) * 1000
                logger.info(
                    f"Request Finished | Status: {response.status_code} | "
                    f"Duration: {process_time:.2f}ms"
                )
                response.headers["X-Trace-ID"] = trace_id
                return response

            except Exception as e:
                process_time = (time.time() - start_time) * 1000
                logger.error(
                    f"Request Failed | Error: {str(e)} | Duration: {process_time:.2f}ms"
                )
                raise e from None
            finally:
                _current_request.reset(token)