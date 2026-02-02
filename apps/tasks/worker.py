"""Task worker: consume tasks from queue and execute."""

import asyncio
import signal
import sys
from typing import Optional
from framework.logging.logger import get_logger
from framework.database.manager import DatabaseManager
from framework.repository.unit_of_work import UnitOfWork
from framework.queue.task_queue import TaskQueue
from framework.config import settings
from .service import TaskService
from .repository import TaskRepository
from .models import Task
from apps.identity.models import User, Tenant
from framework.security import CurrentUser

logger = get_logger("task_worker")


class TaskWorker:
    """Consume task messages from Redis Stream, execute and update status."""

    def __init__(
        self,
        consumer_name: str = "worker-1",
        poll_interval: int = 1,
        max_retries: int = 3,
        worker_id: Optional[str] = None
    ):
        """Initialize worker (consumer_name, poll_interval, max_retries, worker_id)."""
        self.consumer_name = consumer_name
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.worker_id = worker_id
        self.running = False
        self.task_queue: Optional[TaskQueue] = None
        self.db_manager: Optional[DatabaseManager] = None
    
    async def initialize(self):
        """Initialize worker (DB and Redis)."""
        try:
            self.db_manager = DatabaseManager.get_instance()
            await self.db_manager.redis.connect()
            redis_client = self.db_manager.redis.get_client()
            self.task_queue = TaskQueue(redis_client)
            await self.task_queue.initialize()
            await self._recover_pending_tasks()
            
            logger.info(f"Worker {self.consumer_name} initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize worker: {str(e)}")
            raise
    
    async def _recover_pending_tasks(self):
        """Recover pending tasks from DB to Redis on worker start."""
        try:
            logger.info("Starting recovery of pending tasks from database...")
            async for session in self.db_manager.mysql.get_session():
                task_repo = TaskRepository(session)
                pending_tasks = await task_repo.get_pending_async_tasks(limit=1000)
                
                if pending_tasks:
                    recovered_count = await self.task_queue.recover_pending_tasks(pending_tasks)
                    logger.info(
                        f"Recovery completed: {recovered_count} tasks recovered "
                        f"out of {len(pending_tasks)} pending tasks"
                    )
                else:
                    logger.info("No pending tasks found in database")
                
                break
        except Exception as e:
            logger.error(
                f"Failed to recover pending tasks: {str(e)}",
                exc_info=True
            )

    async def process_task(self, message: dict) -> bool:
        """Process a single task. Returns True on success."""
        task_id = message["task_id"]
        task_type = message["task_type"]
        params = message.get("params", {})
        message_id = message["message_id"]
        
        # Extract user info from message for Service
        user_id = int(message.get("user_id", 0))
        tenant_id = int(message.get("tenant_id", 0))
        
        logger.info(
            f"Processing task {task_id} | Type: {task_type} | "
            f"Message ID: {message_id}"
        )
        
        async for session in self.db_manager.mysql.get_session():
            try:
                uow = UnitOfWork(session=session)
                
                # Update task worker_id after claim
                if self.worker_id is not None:
                    task_repo = uow.get_repository(TaskRepository, Task)
                    task = await task_repo.get_by_id(task_id)
                    if task:
                        task.worker_id = self.worker_id
                        await task_repo.update(task)
                        await uow.flush()
                        logger.info(f"Task {task_id} assigned to worker {self.worker_id}")
                
                current_user = CurrentUser(
                    id=user_id,
                    username=f"worker-user-{user_id}",
                    tenant_id=tenant_id,
                    role="system"
                )
                service = TaskService(uow, current_user, task_queue=None)
                
                await service.execute_task_async(
                    task_id=task_id,
                    task_type=task_type,
                    params=params
                )
                await self.task_queue.ack(message_id)
                
                logger.info(f"Task {task_id} processed successfully")
                return True
                
            except Exception as e:
                logger.error(
                    f"Failed to process task {task_id}: {str(e)}",
                    exc_info=True
                )
                raise e
    
    async def run_once(self):
        """Consume one task."""
        try:
            message = await self.task_queue.dequeue(
                consumer_name=self.consumer_name,
                count=1,
                block_ms=self.poll_interval * 1000
            )
            
            if message:
                await self.process_task(message)
            else:
                # No message, keep polling
                await asyncio.sleep(self.poll_interval)
                
        except Exception as e:
            logger.error(f"Error in worker loop: {str(e)}", exc_info=True)
            await asyncio.sleep(self.poll_interval)
    
    async def run(self):
        """Run worker main loop."""
        self.running = True
        logger.info(f"Worker {self.consumer_name} started")
        
        while self.running:
            try:
                await self.run_once()
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in worker: {str(e)}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
        
        logger.info(f"Worker {self.consumer_name} stopped")
    
    async def shutdown(self):
        """Shutdown worker."""
        self.running = False
        if self.db_manager:
            await self.db_manager.redis.disconnect()
        logger.info(f"Worker {self.consumer_name} shutdown complete")


async def main():
    """Worker main entry."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Task Worker")
    parser.add_argument(
        "--consumer-name",
        type=str,
        default=f"worker-{asyncio.get_event_loop().time()}",
        help="Consumer name for this worker instance"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=1,
        help="Poll interval in seconds"
    )
    
    args = parser.parse_args()
    
    worker = TaskWorker(
        consumer_name=args.consumer_name,
        poll_interval=args.poll_interval
    )
    
    shutdown_task_ref = None
    
    def signal_handler(sig, frame):
        nonlocal shutdown_task_ref
        logger.info("Received signal, initiating shutdown...")
        shutdown_task_ref = asyncio.create_task(worker.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await worker.initialize()
        await worker.run()
    except Exception as e:
        logger.error(f"Worker failed: {str(e)}", exc_info=True)
        sys.exit(1)
    finally:
        await worker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

