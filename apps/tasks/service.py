from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, get_type_hints
import inspect
from pydantic import BaseModel
from framework.logging.logger import get_logger
from framework.exceptions.handler import BusinessException
from framework.security import CurrentUser
from framework.repository.unit_of_work import UnitOfWork
from framework.queue.task_queue import TaskQueue
from sqlalchemy.exc import IntegrityError
from .models import Task, TaskStatus
from .plugins import task_registry
from .repository import TaskRepository
from .storage import save_input_params, load_input_params, save_output_result
import uuid

logger = get_logger("task_service")

class TaskService:
    """Task service (sync/async execution and plugin registration)."""
    
    def __init__(
        self, 
        uow: UnitOfWork, 
        current_user: CurrentUser,
        task_queue: Optional[TaskQueue] = None
    ):
        """Initialize TaskService (uow, current_user, optional task_queue)."""
        self.uow = uow
        self.current_user = current_user
        self.task_queue = task_queue
    
    async def get_task_schema(self, task_type: str) -> Dict[str, Any]:
        """Get param schema for task_type. Returns dict of param names and constraints."""
        if task_type not in task_registry:
            raise BusinessException(
                f"Unsupported task type: {task_type}",
                code=400
            )
        plugin = task_registry[task_type]
        validate_method = plugin.validate_params
        try:
            type_hints = get_type_hints(validate_method)
            return_annotation = type_hints.get('return')
        except Exception:
            sig = inspect.signature(validate_method)
            return_annotation = sig.return_annotation
        if inspect.isclass(return_annotation) and issubclass(return_annotation, BaseModel):
            try:
                if hasattr(return_annotation, 'model_json_schema'):
                    schema = return_annotation.model_json_schema()
                elif hasattr(return_annotation, 'schema'):
                    schema = return_annotation.schema()
                else:
                    schema = {}
                properties = schema.get('properties', {})
                required = schema.get('required', [])
                params_info = {}
                for param_name, param_info in properties.items():
                    param_detail = {
                        'type': param_info.get('type', 'unknown'),
                        'description': param_info.get('description', ''),
                        'required': param_name in required
                    }
                    if 'items' in param_info:
                        param_detail['items'] = param_info['items']
                    if 'minLength' in param_info:
                        param_detail['min_length'] = param_info['minLength']
                    if 'maxLength' in param_info:
                        param_detail['max_length'] = param_info['maxLength']
                    if 'minimum' in param_info:
                        param_detail['minimum'] = param_info['minimum']
                    if 'maximum' in param_info:
                        param_detail['maximum'] = param_info['maximum']
                    if 'enum' in param_info:
                        param_detail['enum'] = param_info['enum']
                    if 'default' in param_info:
                        param_detail['default'] = param_info['default']
                    if 'pattern' in param_info:
                        param_detail['pattern'] = param_info['pattern']
                    if 'format' in param_info:
                        param_detail['format'] = param_info['format']
                    
                    params_info[param_name] = param_detail
                
                return {
                    'task_type': task_type,
                    'params': params_info,
                    'required_params': required
                }
            except Exception as e:
                logger.warning(f"Failed to extract schema for {task_type}: {str(e)}")
                raise BusinessException(
                    f"Failed to get param schema for task type {task_type}: {str(e)}",
                    code=500
                )
        else:
            raise BusinessException(
                f"Invalid return type for validate_params of task type {task_type}",
                code=500
            )
    
    async def submit_task(
        self, 
        task_type: str, 
        params: dict, 
        is_sync: bool = True,
        job_name: Optional[str] = None,
        email_to: Optional[str] = None
    ) -> Task:
        """
        Submit task. Returns created Task."""
        if task_type not in task_registry:
            raise BusinessException(
                f"Unsupported task type: {task_type}",
                code=400
            )
        
        plugin = task_registry[task_type]
        
        plugin_is_sync = plugin.is_sync
        if plugin_is_sync is not None:
            is_sync = plugin_is_sync
            logger.info(
                f"Plugin {task_type} specifies is_sync={is_sync}, "
                f"ignoring submitted parameter"
            )
        
        try:
            validated_params = await plugin.validate_params(params)
            if hasattr(validated_params, 'model_dump'):
                params_dict = validated_params.model_dump()
            elif hasattr(validated_params, 'dict'):
                params_dict = validated_params.dict()
            else:
                params_dict = params
        except BusinessException:
            raise
        except Exception as e:
            raise BusinessException(
                f"Parameter validation failed: {str(e)}",
                code=422
            )
        task_repo = self.uow.get_repository(TaskRepository, Task)
        max_retries = 5
        job_id = None
        
        for retry_count in range(max_retries):
            candidate_job_id = uuid.uuid4().hex[:32]
            exists = await task_repo.exists_by_job_id(candidate_job_id)
            
            if not exists:
                job_id = candidate_job_id
                break
            logger.warning(
                f"Job ID collision detected, regenerating ({retry_count + 1}/{max_retries})"
                )
        if job_id is None:
            logger.error(
                f"Failed to generate unique job_id after {max_retries} attempts"
            )
            raise BusinessException(
                "Task creation failed: could not generate unique job_id, please retry later",
                code=500
            )
        
        try:
            task = Task(
                job_id=job_id,
                task_type=task_type,
                status=TaskStatus.PENDING,
                user_id=self.current_user.id,
                tenant_id=self.current_user.tenant_id,
                params=params_dict,
                is_sync=is_sync,
                job_name=job_name,
                email_to=email_to
            )
            await task_repo.create(task)
            await self.uow.flush()
            save_input_params(task_type, task.id, job_id, params_dict)
            
            logger.info(
                f"Task {task.id} submitted | Type: {task_type} | "
                f"User: {self.current_user.username} | Sync: {is_sync}"
            )
            if is_sync:
                await self._execute_task_sync(task, plugin, params_dict, task_repo)
            else:
                if not self.task_queue:
                    raise BusinessException(
                        "Task queue not configured; cannot submit async task",
                        code=500
                    )
                await self.uow.commit()
                enqueued = await self.task_queue.enqueue(
                    task_id=task.id,
                    task_type=task_type,
                    params=params_dict,
                    user_id=self.current_user.id,
                    tenant_id=self.current_user.tenant_id
                )
                
                if not enqueued:
                    logger.warning(
                        f"Task {task.id} persisted but failed to enqueue. "
                        f"It may be processed later via recovery mechanism."
                    )
                
                logger.info(f"Task {task.id} queued for async execution")
                return task
            await self.uow.commit()
            if task.status == TaskStatus.COMPLETED and getattr(task, "email_to", None):
                await self._notify_task_completed(task)
            
            return task
            
        except BusinessException:
            await self.uow.rollback()
            raise
        except Exception as e:
            await self.uow.rollback()
            logger.error(f"Failed to submit task: {str(e)}")
            raise BusinessException(
                "Task submission failed: internal error",
                code=500
            )
    
    async def _execute_task_sync(
        self, 
        task: Task, 
        plugin, 
        params: dict,
        task_repo: TaskRepository
    ):
        """
        Sync execute task (task, plugin, params, task_repo)."""
        try:
            if not params:
                loaded_params = load_input_params(task.task_type, task.id, task.job_id)
                if loaded_params is None:
                    raise BusinessException(
                        f"Input params file for task {task.id} not found",
                        code=404
                    )
                params = loaded_params
            
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            await task_repo.update(task)
            await self.uow.flush()
            logger.info(f"Task {task.id} started execution")
            result = plugin.execute(task.id, params)
            save_output_result(task.task_type, task.id, task.job_id, result)
            
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            await task_repo.update(task)
            
            logger.info(f"Task {task.id} completed successfully")
            
        except BusinessException:
            # Business exception, record error
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(timezone.utc)
            await task_repo.update(task)
            raise
        except Exception as e:
            # System exception, record error
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            await task_repo.update(task)
            logger.error(f"Task {task.id} failed: {str(e)}")
            raise BusinessException(
                f"Task execution failed: {str(e)}",
                code=500
            )

    async def get_task(self, job_id: str) -> Task:
        """
        Get task by job_id (result excludes path key)."""
        task_repo = self.uow.get_repository(TaskRepository, Task)
        task = await task_repo.get_by_job_id_and_tenant(
            job_id, 
            self.current_user.tenant_id
        )
        
        if not task:
            raise BusinessException("Task not found or no permission", code=404)
        _ = task.result
        
        return task
    
    async def list_tasks(
        self, 
        limit: int = 20, 
        offset: int = 0,
        status: Optional[TaskStatus] = None
    ) -> List[Task]:
        """
        List tasks for current user (newest first, optional status filter)."""
        task_repo = self.uow.get_repository(TaskRepository, Task)
        return await task_repo.list_by_user(
            user_id=self.current_user.id,
            tenant_id=self.current_user.tenant_id,
            limit=limit,
            offset=offset,
            status=status
        )
    
    async def execute_task_async(
        self,
        task_id: int,
        task_type: str,
        params: dict
    ) -> None:
        """
        Execute task async (called by Worker)."""
        if task_type not in task_registry:
            raise BusinessException(
                f"Unsupported task type: {task_type}",
                code=400
            )
        
        plugin = task_registry[task_type]
        task_repo = self.uow.get_repository(TaskRepository, Task)
        
        try:
            task = await task_repo.get_by_id(task_id)
            if not task:
                raise BusinessException(f"Task {task_id} not found", code=404)
            
            if task.status != TaskStatus.PENDING:
                logger.warning(
                    f"Task {task_id} is not in PENDING status, "
                    f"current status: {task.status}"
                )
                return
            if not params:
                logger.warning(
                    f"Task {task_id} params not found in Redis message, "
                    f"trying to load from file as fallback"
                )
                loaded_params = load_input_params(task_type, task_id, task.job_id)
                if loaded_params is None:
                    raise BusinessException(
                        f"Input params for task {task_id} not found (Redis and filesystem)",
                        code=404
                    )
                params = loaded_params
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            await task_repo.update(task)
            await self.uow.flush()
            logger.info(f"Task {task_id} started async execution")
            result = plugin.execute(task_id, params)
            save_output_result(task_type, task_id, task.job_id, result)
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            await task_repo.update(task)
            await self.uow.commit()
            if getattr(task, "email_to", None):
                await self._notify_task_completed(task)
            
            logger.info(f"Task {task_id} completed successfully")
        except BusinessException:
            task = await task_repo.get_by_id(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now(timezone.utc)
                await task_repo.update(task)
                await self.uow.commit()
            raise
        except Exception as e:
            task = await task_repo.get_by_id(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                task.completed_at = datetime.now(timezone.utc)
                await task_repo.update(task)
                await self.uow.commit()
            logger.error(f"Task {task_id} failed: {str(e)}")
            raise BusinessException(
                f"Task execution failed: {str(e)}",
                code=500
            )

    async def _notify_task_completed(self, task: Task) -> None:
        """
        Optional task completion notification (failure does not affect main flow)."""
        try:
            from framework.notification.notifier import notify_task_completed
            await notify_task_completed(
                email_to=task.email_to,
                job_id=task.job_id,
                task_type=task.task_type,
                job_name=getattr(task, "job_name", None),
                tenant_id=task.tenant_id,
                user_id=task.user_id
            )
        except Exception as e:
            logger.warning(f"Failed to send completion notification for task {task.id}: {str(e)}")

