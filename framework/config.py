import os
from typing import Optional
from urllib.parse import quote_plus
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Basic configuration ---
    APP_NAME: str = "FastAPI App"
    APP_DESCRIPTION: str = "Production-ready FastAPI application with auth, task queue, and plugin support"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"  # development, production, testing
    DEBUG: bool = True
    SECRET_KEY: str = "your-super-secret-key-change-it-in-production"
    
    # --- Database (MySQL/SQLModel) ---
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "root"
    DB_NAME: str = "app_db"
    
    @property
    def DATABASE_URL(self) -> str:
        # Build async MySQL connection URL
        safe_password = quote_plus(self.DB_PASSWORD)
        return f"mysql+aiomysql://{self.DB_USER}:{safe_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # --- Cache and task queue (Redis) ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # --- Quotas and resource limits (defaults) ---
    DEFAULT_MAX_TASKS: int = 20
    DEFAULT_STORAGE_GB: int = 10

    # --- Notification service ---
    NOTIFICATION_DRIVER: str = "mock"  # mock, email, sms
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    
    # --- Cookie ---
    ACCESS_TOKEN_COOKIE_NAME: str = "access_token"
    COOKIE_SECURE: bool = False  # Set True in production (HTTPS only)
    COOKIE_SAMESITE: str = "lax"  # lax, strict, none

    # --- Logging ---
    LOG_DIR: str = "logs"
    
    # --- Task workspace ---
    JOB_WORKSPACE: str = "job_workspace"  # Root directory for task files

    # --- Task queue (Redis Stream) ---
    TASK_QUEUE_STREAM_NAME: str = "tasks:queue"
    TASK_QUEUE_CONSUMER_GROUP: str = "tasks:workers"

    # --- API route prefixes (optional, overridable in private projects) ---
    API_V1_AUTH_PREFIX: str = "/api/v1/auth"
    API_V1_TASKS_PREFIX: str = "/api/v1/tasks"

    # --- Gunicorn process name (optional) ---
    GUNICORN_PROC_NAME: Optional[str] = None  # Fallback to APP_NAME when empty

    # --- Pydantic ---
    # Load env from project root .env; priority: env vars > .env > defaults
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )
    

# Singleton settings instance
settings = Settings()