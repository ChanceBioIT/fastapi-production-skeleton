from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import Optional
from framework.database.manager import DatabaseManager
from framework.repository.unit_of_work import UnitOfWork
from framework.queue.task_queue import TaskQueue
from framework.security import get_current_user, CurrentUser
from framework.response import ResponseModel
from ..service import TaskService
from pydantic import BaseModel

router = APIRouter()

# Unified task submission schema
class TaskSubmission(BaseModel):
    task_type: str
    params: Optional[dict] = None
    is_sync: Optional[bool] = True
    help: Optional[bool] = False
    job_name: Optional[str] = None
    email_to: Optional[str] = None

async def get_db():
    """Get database session."""
    manager = DatabaseManager.get_instance()
    async for session in manager.mysql.get_session():
        yield session

def get_uow(
    db: AsyncSession = Depends(get_db)
) -> UnitOfWork:
    """Dependency: create UnitOfWork."""
    return UnitOfWork(session=db)

async def get_task_queue() -> TaskQueue:
    """Dependency: create task queue."""
    manager = DatabaseManager.get_instance()
    redis_client = manager.redis.get_client()
    if not redis_client:
        await manager.redis.connect()
        redis_client = manager.redis.get_client()
    
    queue = TaskQueue(redis_client)
    await queue.initialize()
    return queue

def get_task_service(
    uow: UnitOfWork = Depends(get_uow),
    current_user: CurrentUser = Depends(get_current_user),
    task_queue: TaskQueue = Depends(get_task_queue)
) -> TaskService:
    """Dependency: create TaskService."""
    return TaskService(uow, current_user, task_queue)

@router.post("/submit")
async def submit_task(
    payload: TaskSubmission,
    service: TaskService = Depends(get_task_service)
):
    """Unified task entry for all registered plugins. When help=True, returns param schema for task_type."""
    if payload.help:
        schema_info = await service.get_task_schema(payload.task_type)
        return ResponseModel.success(data=schema_info)
    if payload.params is None:
        return ResponseModel.error(
            message="params cannot be empty (unless help=True)",
            code=400
        )
    
    task_record = await service.submit_task(
        task_type=payload.task_type,
        params=payload.params,
        is_sync=payload.is_sync if payload.is_sync is not None else True,
        job_name=payload.job_name,
        email_to=payload.email_to
    )
    
    return ResponseModel.success(data=task_record)

@router.get("/list")
async def list_tasks(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    service: TaskService = Depends(get_task_service)
):
    """List tasks for current user (newest first, optional status filter)."""
    from ..models import TaskStatus
    
    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status)
        except ValueError:
            return ResponseModel.error(
                message=f"Invalid task status: {status}",
                code=400
            )
    
    tasks = await service.list_tasks(
        limit=limit,
        offset=offset,
        status=status_filter
    )
    
    return ResponseModel.success(data=tasks)

@router.get("/{job_id}")
async def get_task(
    job_id: str,
    service: TaskService = Depends(get_task_service)
):
    """Get task detail (status and result; result from output.json excluding path)."""
    task = await service.get_task(job_id)
    if hasattr(task, 'model_dump'):
        task_dict = task.model_dump()
    elif hasattr(task, 'dict'):
        task_dict = task.dict()
    else:
        task_dict = {
            "id": task.id,
            "job_id": task.job_id,
            "task_type": task.task_type,
            "status": task.status,
            "user_id": task.user_id,
            "tenant_id": task.tenant_id,
            "params": task.params,
            "error_message": task.error_message,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "is_sync": task.is_sync,
        }
    
    task_dict["job_name"] = task.job_name
    task_dict["email_to"] = task.email_to
    task_dict["result"] = task.result
    
    return ResponseModel.success(data=task_dict)