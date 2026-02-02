#!/usr/bin/env python3
"""
Background task execution script.

Usage:
    python -m apps.tasks.scripts.run_task --task-id <task_id>
    or
    python -m apps.tasks.scripts.run_task --job-id <job_id>

Features:
    1. Look up task in DB by task_id or job_id
    2. Run corresponding plugin by task_type
    3. Update task status in DB when done
"""

import asyncio
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from framework.database.manager import DatabaseManager
from framework.repository.unit_of_work import UnitOfWork
from framework.logging.logger import get_logger
from framework.exceptions.handler import BusinessException
from apps.tasks.models import Task, TaskStatus
from apps.tasks.repository import TaskRepository
from apps.tasks.plugins import task_registry
from apps.tasks.storage import load_input_params, save_output_result

logger = get_logger("run_task_script")


def _normalize_task_status(status_value) -> TaskStatus:
    """Normalize task status (handle enum conversion)."""
    if isinstance(status_value, TaskStatus):
        return status_value
    if isinstance(status_value, str):
        status_str = status_value.lower()
        for status in TaskStatus:
            if status.value == status_str:
                return status
        try:
            return TaskStatus[status_str.upper()]
        except KeyError:
            logger.warning(f"Unknown task status: {status_value}, using PENDING as default")
            return TaskStatus.PENDING
    
    return TaskStatus.PENDING


async def get_task_by_id_or_job_id(
    task_id: int = None,
    job_id: str = None
) -> Task:
    """Look up task by task_id or job_id. Raises BusinessException if not found."""
    db_manager = DatabaseManager.get_instance()
    task = None
    async with db_manager.mysql.session_factory() as session:
        task_repo = TaskRepository(session)
        if task_id:
            task = await task_repo.get_by_id(task_id)
        elif job_id:
            from sqlmodel import select
            statement = select(Task).where(Task.job_id == job_id).limit(1)
            result = await session.exec(statement)
            task = result.first()
        else:
            raise ValueError("Must provide task_id or job_id")
    if not task:
        identifier = f"task_id={task_id}" if task_id else f"job_id={job_id}"
        raise BusinessException(f"Task not found: {identifier}", code=404)
    
    return task


def _get_task_params(current_task: Task) -> dict:
    """Get task params (prefer DB, fallback to file)."""
    params = current_task.params if current_task.params else {}
    if not params:
        loaded_params = load_input_params(
            current_task.task_type,
            current_task.id,
            current_task.job_id
        )
        if loaded_params:
            params = loaded_params
            logger.info(f"Loaded params from file for task {current_task.id}")
        else:
            logger.warning(
                f"No params found in database or file for task {current_task.id}, "
                f"using empty params"
            )
    return params


async def _prepare_task_for_execution(
    task_repo: TaskRepository,
    task_id: int,
    session,
    force: bool = False
) -> Task:
    """Prepare task: fetch and set status to RUNNING."""
    current_task = await task_repo.get_by_id(task_id)
    if not current_task:
        raise BusinessException(f"Task {task_id} not found", code=404)
    try:
        current_task.status = _normalize_task_status(current_task.status)
    except Exception as e:
        logger.warning(f"Failed to normalize task status: {e}, using raw value")
    
    if not force and current_task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
        logger.warning(
            f"Task {current_task.id} is not in PENDING or RUNNING status, "
            f"current status: {current_task.status}. Use --force to execute anyway."
        )
        return None
    
    if force and current_task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
        logger.warning(
            f"Force executing task {current_task.id} with status: {current_task.status}"
        )
    
    started_at = datetime.now(timezone.utc)
    from sqlmodel import update
    
    stmt = (
        update(Task)
        .where(Task.id == task_id)
        .values(
            status=TaskStatus.RUNNING,
            started_at=started_at
        )
    )
    await session.exec(stmt)
    await session.commit()
    
    current_task = await task_repo.get_by_id(task_id)
    current_task.status = TaskStatus.RUNNING
    current_task.started_at = started_at
    
    logger.info(f"Task {current_task.id} started execution")
    return current_task


async def _complete_task_successfully(
    current_task: Task,
    result: dict,
    session
):
    """Complete task: save result and set status to COMPLETED."""
    save_output_result(
        current_task.task_type,
        current_task.id,
        current_task.job_id,
        result
    )
    from sqlmodel import update
    completed_at = datetime.now(timezone.utc)
    stmt = (
        update(Task)
        .where(Task.id == current_task.id)
        .values(
            status=TaskStatus.COMPLETED,
            completed_at=completed_at
        )
    )
    await session.exec(stmt)
    await session.commit()
    
    logger.info(
        f"Task {current_task.id} completed successfully | "
        f"Result keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}"
    )


async def execute_task(task: Task, force: bool = False) -> bool:
    """Execute task. Returns True on success."""
    if task.task_type not in task_registry:
        raise BusinessException(
            f"Unsupported task type: {task.task_type}",
            code=400
        )
    plugin = task_registry[task.task_type]
    db_manager = DatabaseManager.get_instance()
    async with db_manager.mysql.session_factory() as session:
        try:
            uow = UnitOfWork(session=session)
            task_repo = uow.get_repository(TaskRepository, Task)
            current_task = await _prepare_task_for_execution(task_repo, task.id, session, force=force)
            if not current_task:
                return False
            params = _get_task_params(current_task)
            logger.info(
                f"Executing task {current_task.id} | Type: {current_task.task_type} | "
                f"Params keys: {list(params.keys()) if params else 'empty'}"
            )
            
            result = plugin.execute(current_task.id, params)
            await _complete_task_successfully(current_task, result, session)
            return True
        except BusinessException as e:
            await _handle_task_failure(session, task.id, e)
            raise
        except Exception as e:
            await _handle_task_failure(session, task.id, e)
            error_msg = str(e)
            logger.error(f"Task {task.id} failed: {error_msg}", exc_info=True)
            raise BusinessException(
                f"Task execution failed: {error_msg}",
                code=500
            )


async def _handle_task_failure(session, task_id: int, error: Exception):
    """On task failure: set status to FAILED."""
    try:
        error_message = error.message if hasattr(error, 'message') else str(error)
        await update_task_status(
            session,
            task_id,
            TaskStatus.FAILED,
            error_message=error_message
        )
    except Exception:
        pass


async def update_task_status(
    session,
    task_id: int,
    status: TaskStatus,
    error_message: str = None
):
    """Update task status (direct SQL update)."""
    try:
        from sqlmodel import update
        completed_at = datetime.now(timezone.utc)
        
        if error_message:
            # Update status, completed_at, error_message
            stmt = (
                update(Task)
                .where(Task.id == task_id)
                .values(
                    status=status,
                    completed_at=completed_at,
                    error_message=error_message
                )
            )
        else:
            # Update status and completed_at only
            stmt = (
                update(Task)
                .where(Task.id == task_id)
                .values(
                    status=status,
                    completed_at=completed_at
                )
            )
        
        await session.exec(stmt)
        await session.commit()
        logger.info(f"Task {task_id} status updated to {status}")
    except Exception as e:
        await session.rollback()
        logger.error(f"Failed to update task {task_id} status: {str(e)}", exc_info=True)


async def main():
    """Main entry."""
    parser = argparse.ArgumentParser(
        description="Background task execution script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m apps.tasks.scripts.run_task --task-id 123
  python -m apps.tasks.scripts.run_task --job-id abc123def456...
  python -m apps.tasks.scripts.run_task --task-id 123 --force
        """
    )
    
    parser.add_argument(
        "--task-id",
        type=int,
        help="Task ID (DB primary key)"
    )
    
    parser.add_argument(
        "--job-id",
        type=str,
        help="Task job_id (32-char UUID)"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force run task, ignore status check"
    )
    
    args = parser.parse_args()
    
    if not args.task_id and not args.job_id:
        parser.error("Must provide --task-id or --job-id")
    if args.task_id and args.job_id:
        parser.error("Cannot provide both --task-id and --job-id")
    
    db_manager = None
    exit_code = 1
    
    try:
        db_manager = DatabaseManager.get_instance()
        await db_manager.mysql.connect()
        
        logger.info("=" * 60)
        logger.info("Task Execution Script Started")
        logger.info("=" * 60)
        
        identifier = f"task_id={args.task_id}" if args.task_id else f"job_id={args.job_id}"
        logger.info(f"Querying task with {identifier}...")
        
        task = await get_task_by_id_or_job_id(
            task_id=args.task_id,
            job_id=args.job_id
        )
        
        try:
            normalized_status = _normalize_task_status(task.status)
            status_str = normalized_status.value if isinstance(normalized_status, TaskStatus) else str(task.status)
        except Exception:
            status_str = str(task.status)
        
        logger.info(
            f"Task found: ID={task.id}, JobID={task.job_id}, "
            f"Type={task.task_type}, Status={status_str}"
        )
        
        if args.force:
            logger.info("Force mode enabled: will execute task regardless of status")
        
        logger.info("Starting task execution...")
        success = await execute_task(task, force=args.force)
        
        if success:
            logger.info("=" * 60)
            logger.info("Task Execution Completed Successfully")
            logger.info("=" * 60)
            exit_code = 0
        else:
            logger.warning("Task execution skipped (status check failed)")
            exit_code = 1
            
    except BusinessException as e:
        logger.error(f"Business error: {e.message}")
        exit_code = 1
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        exit_code = 1
    finally:
        if db_manager:
            try:
                import asyncio
                await asyncio.sleep(0.1)
                await db_manager.mysql.disconnect()
            except Exception as e:
                logger.debug(f"Error disconnecting database: {e}")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
