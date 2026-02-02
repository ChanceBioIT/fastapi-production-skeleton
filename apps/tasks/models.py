from sqlmodel import SQLModel, Field, Column, JSON
from typing import Optional, Dict
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import String
from ..identity.models import User, Tenant
import uuid

class TaskStatus(str, Enum):
    """Task status enum."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class Task(SQLModel, table=True):
    """Task model (sync/async and plugin execution)."""
    __tablename__ = "tasks"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:32],
        unique=True,
        index=True,
        max_length=32,
        description="Task unique id (32-char)"
    )
    task_type: str = Field(index=True, description="Task type, e.g. seq_toolkit")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Task status")

    job_name: Optional[str] = Field(
        default=None,
        max_length=255,
        sa_column=Column(String(255), nullable=True),
        description="Job display name"
    )
    email_to: Optional[str] = Field(
        default=None,
        max_length=320,
        sa_column=Column(String(320), nullable=True),
        description="Completion notification email"
    )

    user_id: int = Field(foreign_key="users.id", index=True)
    tenant_id: int = Field(foreign_key="tenants.id", index=True)

    params: Dict = Field(default_factory=dict, sa_column=Column(JSON), description="Task params")
    error_message: Optional[str] = Field(default=None, description="Error message")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Created at")
    started_at: Optional[datetime] = Field(default=None, description="Started at")
    completed_at: Optional[datetime] = Field(default=None, description="Completed at")

    is_sync: bool = Field(default=True, description="Sync execution")
    worker_id: Optional[str] = Field(
        default=None,
        max_length=100,
        sa_column=Column(String(100), nullable=True, index=True),
        description="Worker ID that processed this task"
    )

    @property
    def result(self) -> Optional[Dict]:
        """Load task result from file (excludes path key)."""
        from .storage import load_output_result
        if self.id is None:
            return None
        result = load_output_result(self.task_type, self.id, self.job_id)
        if result is None:
            return None
        if isinstance(result, dict):
            result = {k: v for k, v in result.items() if k != "path"}
        return result

