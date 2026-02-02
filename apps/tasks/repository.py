"""Task module repository implementation."""

from typing import Optional, List
from framework.repository.base import BaseRepository
from .models import Task, TaskStatus


class TaskRepository(BaseRepository[Task]):
    """Task repository."""
    
    def __init__(self, session):
        super().__init__(session, Task)
    
    async def get_by_id_and_tenant(
        self, 
        task_id: int, 
        tenant_id: int
    ) -> Optional[Task]:
        """Get task by task_id and tenant_id (tenant isolation)."""
        return await self.find_one(id=task_id, tenant_id=tenant_id)
    
    async def get_by_job_id_and_tenant(
        self, 
        job_id: str, 
        tenant_id: int
    ) -> Optional[Task]:
        """
        Get task by job_id and tenant_id (tenant isolation).
        
        Args:
            job_id: Task job_id (32-char UUID)
            tenant_id: Tenant ID
        
        Returns:
            Task entity or None
        """
        return await self.find_one(job_id=job_id, tenant_id=tenant_id)
    
    async def exists_by_job_id(self, job_id: str) -> bool:
        """Check if job_id exists (global uniqueness)."""
        from sqlmodel import select
        
        statement = select(Task).where(Task.job_id == job_id).limit(1)
        result = await self.session.exec(statement)
        task = result.first()
        return task is not None
    
    async def list_by_tenant(
        self,
        tenant_id: int,
        limit: int = 20,
        offset: int = 0,
        status: Optional[TaskStatus] = None
    ) -> List[Task]:
        """List tasks by tenant_id with optional status filter."""
        from sqlmodel import select
        
        statement = select(Task).where(Task.tenant_id == tenant_id)
        
        if status:
            statement = statement.where(Task.status == status)
        
        statement = statement.order_by(Task.created_at.desc())
        statement = statement.limit(limit).offset(offset)
        
        result = await self.session.exec(statement)
        return list(result.all())
    
    async def list_by_user(
        self,
        user_id: int,
        tenant_id: int,
        limit: int = 20,
        offset: int = 0,
        status: Optional[TaskStatus] = None
    ) -> List[Task]:
        """
        List tasks by user_id and tenant_id (optional status filter).
        Returns only the current user's tasks, ordered by creation time descending.
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID (tenant isolation)
            limit: Page size
            offset: Offset
            status: Optional task status filter
        
        Returns:
            List of tasks (by creation time descending)
        """
        from sqlmodel import select
        
        statement = select(Task).where(
            Task.user_id == user_id,
            Task.tenant_id == tenant_id
        )
        
        if status:
            statement = statement.where(Task.status == status)
        
        statement = statement.order_by(Task.created_at.desc())
        statement = statement.limit(limit).offset(offset)
        
        result = await self.session.exec(statement)
        return list(result.all())
    
    async def count_by_tenant(
        self,
        tenant_id: int,
        status: Optional[TaskStatus] = None
    ) -> int:
        """
        Count tasks for a tenant.
        
        Args:
            tenant_id: Tenant ID
            status: Optional task status filter
        
        Returns:
            Task count
        """
        from sqlmodel import select, func
        
        statement = select(func.count(Task.id)).where(
            Task.tenant_id == tenant_id
        )
        
        if status:
            statement = statement.where(Task.status == status)
        
        result = await self.session.exec(statement)
        return result.one()
    
    async def get_pending_async_tasks(self, limit: int = 1000) -> List[Task]:
        """Get pending async tasks (status=PENDING, is_sync=False) for recovery."""
        from sqlmodel import select
        
        statement = select(Task).where(
            Task.status == TaskStatus.PENDING,
            Task.is_sync == False
        ).order_by(Task.created_at.asc()).limit(limit)
        
        result = await self.session.exec(statement)
        return list(result.all())

