from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from framework.config import settings
from framework.response import ResponseModel
from framework.middleware.logging_md import LoggingMiddleware
from framework.logging.logger import LogConfig
from framework.exceptions.handler import BusinessException, global_exception_handler
from apps.identity.api.router import router as identity_router
from apps.tasks.api.router import router as task_router

app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Initialize logging configuration
LogConfig.setup_logging()

# Register global exception handlers
app.add_exception_handler(BusinessException, global_exception_handler)
app.add_exception_handler(RequestValidationError, global_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

app.add_middleware(LoggingMiddleware)

# Mount routers (prefix from config for easy override in private projects)
app.include_router(
    identity_router,
    prefix=settings.API_V1_AUTH_PREFIX,
    tags=["Identity & Tenant"]
)

app.include_router(
    task_router,
    prefix=settings.API_V1_TASKS_PREFIX,
    tags=["Tasks"]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
