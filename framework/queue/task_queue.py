"""
Reliable task queue using Redis Stream + Database (DB-First).

Features:
- DB-First: save task to DB first, then push to Redis
- Reliable consumption: consumer groups and PEL to avoid message loss
- Fault tolerance: XCLAIM for stuck tasks, compensation for lost tasks
- Connection pool and error handling
"""

import json
import asyncio
from typing import Optional, Dict, Any, List, Callable, Awaitable
from datetime import datetime, timezone, timedelta
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import ConnectionError as RedisConnectionError, ResponseError
from framework.config import settings
from framework.logging.logger import get_logger

logger = get_logger("task_queue")


class TaskQueue:
    """
    Reliable task queue (DB-First):
    1. Producer: save to DB (PENDING) -> push to Redis Stream
    2. Consumer: read from Redis -> update DB -> run logic -> ACK
    3. Fault tolerance: XCLAIM for stuck tasks, compensation for lost tasks
    """

    PENDING_TIMEOUT_MS = 5 * 60 * 1000  # Pending message timeout (5 min)
    COMPENSATION_INTERVAL_SECONDS = 60   # Compensation scan interval (60 s)
    COMPENSATION_THRESHOLD_MINUTES = 5   # Compensation threshold (5 min)

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        redis_pool: Optional[ConnectionPool] = None,
        pending_timeout_ms: int = None,
        compensation_interval: int = None,
        compensation_threshold: int = None
    ):
        """Initialize task queue. Provide redis_client or redis_pool."""
        if redis_client:
            self.redis = redis_client
            self._own_redis = False
        elif redis_pool:
            self.redis = redis.Redis(connection_pool=redis_pool)
            self._own_redis = False
        else:
            raise ValueError("Either redis_client or redis_pool must be provided")

        self.stream_name = settings.TASK_QUEUE_STREAM_NAME
        self.consumer_group = settings.TASK_QUEUE_CONSUMER_GROUP
        
        if pending_timeout_ms is not None:
            self.PENDING_TIMEOUT_MS = pending_timeout_ms
        if compensation_interval is not None:
            self.COMPENSATION_INTERVAL_SECONDS = compensation_interval
        if compensation_threshold is not None:
            self.COMPENSATION_THRESHOLD_MINUTES = compensation_threshold
        
        self._compensation_task: Optional[asyncio.Task] = None
        self._compensation_callback: Optional[Callable[[], Awaitable[List[int]]]] = None
    
    async def initialize(self):
        """Create consumer group if it does not exist."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                groups = await self.redis.xinfo_groups(self.stream_name)
                group_names = [
                    g['name'].decode() if isinstance(g['name'], bytes) else g['name']
                    for g in groups
                ]
                
                if self.consumer_group not in group_names:
                    await self.redis.xgroup_create(
                        name=self.stream_name,
                        groupname=self.consumer_group,
                        id="0",
                        mkstream=True
                    )
                    logger.info(f"Created consumer group: {self.consumer_group}")
                else:
                    logger.debug(f"Consumer group {self.consumer_group} already exists")
                
                return
                
            except ResponseError as e:
                error_str = str(e)
                if "no such key" in error_str.lower():
                    try:
                        await self.redis.xgroup_create(
                            name=self.stream_name,
                            groupname=self.consumer_group,
                            id="0",
                            mkstream=True
                        )
                        logger.info(f"Created stream and consumer group: {self.consumer_group}")
                        return
                    except ResponseError as create_error:
                        if "BUSYGROUP" not in str(create_error):
                            if attempt == max_retries - 1:
                                raise
                            await asyncio.sleep(0.1 * (attempt + 1))
                            continue
                        logger.debug(f"Consumer group {self.consumer_group} already exists")
                        return
                elif "BUSYGROUP" in error_str:
                    logger.debug(f"Consumer group {self.consumer_group} already exists")
                    return
                else:
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(0.1 * (attempt + 1))
                    
            except RedisConnectionError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to connect to Redis after {max_retries} attempts: {str(e)}")
                    raise
                logger.warning(f"Redis connection error (attempt {attempt + 1}/{max_retries}): {str(e)}")
                await asyncio.sleep(0.5 * (attempt + 1))
    
    async def enqueue(self, task_id: int, task_type: str, **metadata) -> bool:
        """
        Producer: push task to Redis Stream. Task must already be saved to DB with status PENDING.
        Returns True if enqueued successfully.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                message_data = {
                    "task_id": str(task_id),
                    "task_type": task_type,
                    "enqueued_at": datetime.now(timezone.utc).isoformat(),
                }
                
                for k, v in metadata.items():
                    if k == "params" and isinstance(v, dict):
                        message_data["params"] = json.dumps(v)
                    else:
                        message_data[k] = str(v)

                message_id = await self.redis.xadd(
                    self.stream_name,
                    message_data,
                    maxlen=10000
                )
                
                logger.info(
                    f"Task {task_id} enqueued to Redis | Type: {task_type} | "
                    f"Message ID: {message_id}"
                )
                
                return True
                
            except RedisConnectionError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to enqueue task {task_id} after {max_retries} attempts: {str(e)}")
                    return False
                logger.warning(f"Redis connection error while enqueuing (attempt {attempt + 1}/{max_retries}): {str(e)}")
                await asyncio.sleep(0.5 * (attempt + 1))
                
            except Exception as e:
                logger.error(f"Failed to enqueue task {task_id}: {str(e)}", exc_info=True)
                return False
        
        return False
    
    async def dequeue(
        self,
        consumer_name: str,
        count: int = 1,
        block_ms: int = 5000
    ) -> Optional[Dict[str, Any]]:
        """
        Consumer: read from Redis Stream. Process PEL first (recovery), then new messages.
        Returns message dict with task_id, task_type, message_id, etc.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Step 1: process PEL (recovery after worker restart)
                pel_messages = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=consumer_name,
                    streams={self.stream_name: "0"},
                    count=count,
                    block=0
                )

                if pel_messages and pel_messages[0][1]:
                    _, message_list = pel_messages[0]
                    if message_list:
                        message_id, message_data = message_list[0]
                        parsed = self._parse_message(message_id, message_data)
                        logger.info(
                            f"Retrieved PEL message {parsed['message_id']} "
                            f"for consumer {consumer_name}"
                        )
                        return parsed
                
                # Step 2: read new messages
                new_messages = await self.redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=consumer_name,
                    streams={self.stream_name: ">"},
                    count=count,
                    block=block_ms
                )
                
                if new_messages and new_messages[0][1]:
                    _, message_list = new_messages[0]
                    if message_list:
                        message_id, message_data = message_list[0]
                        parsed = self._parse_message(message_id, message_data)
                        logger.info(
                            f"Retrieved new message {parsed['message_id']} "
                            f"for consumer {consumer_name}"
                        )
                        return parsed
                
                # Step 3: try to claim timeout messages from other consumers
                claimed = await self._claim_stuck_messages(consumer_name, count)
                if claimed:
                    return claimed
                
                return None
                
            except RedisConnectionError as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to dequeue after {max_retries} attempts: {str(e)}"
                    )
                    return None
                logger.warning(
                    f"Redis connection error while dequeuing "
                    f"(attempt {attempt + 1}/{max_retries}): {str(e)}"
                )
                await asyncio.sleep(0.5 * (attempt + 1))
                
            except Exception as e:
                logger.error(f"Failed to dequeue: {str(e)}", exc_info=True)
                return None
        
        return None
    
    async def _claim_stuck_messages(
        self,
        consumer_name: str,
        count: int = 1
    ) -> Optional[Dict[str, Any]]:
        """Claim timeout messages from other consumers (XCLAIM)."""
        try:
            all_pending = await self.redis.xpending_range(
                self.stream_name,
                self.consumer_group,
                min="-",
                max="+",
                count=100
            )

            if not all_pending:
                return None

            for pending_msg in all_pending:
                time_since_delivered = pending_msg.get("time_since_delivered", 0)
                
                if time_since_delivered >= self.PENDING_TIMEOUT_MS:
                    pending_msg_id = pending_msg["message_id"]
                    if isinstance(pending_msg_id, bytes):
                        pending_msg_id = pending_msg_id.decode()
                    
                    original_consumer = pending_msg.get("consumer", b"")
                    if isinstance(original_consumer, bytes):
                        original_consumer = original_consumer.decode()
                    
                    if original_consumer == consumer_name:
                        continue

                    try:
                        claimed_messages = await self.redis.xclaim(
                            name=self.stream_name,
                            groupname=self.consumer_group,
                            consumername=consumer_name,
                            min_idle_time=self.PENDING_TIMEOUT_MS,
                            message_ids=[pending_msg_id]
                        )
                        
                        if claimed_messages:
                            _, msg_data = claimed_messages[0]
                            parsed = self._parse_message(pending_msg_id, msg_data)
                            
                            logger.info(
                                f"Claimed stuck message {parsed['message_id']} "
                                f"from {original_consumer} to {consumer_name}, "
                                f"idle_time: {time_since_delivered}ms"
                            )
                            
                            return parsed
                            
                    except Exception as e:
                        logger.warning(
                            f"Failed to claim message {pending_msg_id}: {str(e)}"
                        )
                        continue
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to claim stuck messages: {str(e)}", exc_info=True)
            return None
    
    def _parse_message(self, message_id, message_data: dict) -> Dict[str, Any]:
        """Parse Redis Stream message into dict."""
        parsed = {}
        for key, value in message_data.items():
            key_str = key.decode() if isinstance(key, bytes) else key
            value_str = value.decode() if isinstance(value, bytes) else value
            
            if key_str == "params":
                try:
                    parsed[key_str] = json.loads(value_str)
                except (json.JSONDecodeError, TypeError):
                    parsed[key_str] = value_str
            else:
                parsed[key_str] = value_str
        
        message_id_str = message_id.decode() if isinstance(message_id, bytes) else message_id
        
        return {
            "message_id": message_id_str,
            "task_id": int(parsed["task_id"]),
            "task_type": parsed["task_type"],
            **{k: v for k, v in parsed.items() if k not in ["task_id", "task_type"]}
        }
    
    async def ack(self, message_id: str) -> bool:
        """Ack message (XACK). Returns True on success."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.redis.xack(
                    self.stream_name,
                    self.consumer_group,
                    message_id
                )
                return True
                
            except RedisConnectionError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to ack message {message_id} after {max_retries} attempts: {str(e)}")
                    return False
                await asyncio.sleep(0.5 * (attempt + 1))
                
            except Exception as e:
                logger.error(f"Failed to ack message {message_id}: {str(e)}", exc_info=True)
                return False
        
        return False
    
    def register_compensation_callback(
        self,
        callback: Callable[[], Awaitable[List[int]]]
    ):
        """Register compensation callback; it should return task IDs that are PENDING and over threshold."""
        self._compensation_callback = callback

    async def _is_task_in_stream(self, task_id: int) -> bool:
        """Check if task is in Redis Stream."""
        try:
            all_pending = await self.redis.xpending_range(
                self.stream_name,
                self.consumer_group,
                min="-",
                max="+",
                count=1000
            )
            
            for pending_msg in all_pending:
                msg_id = pending_msg["message_id"]
                if isinstance(msg_id, bytes):
                    msg_id = msg_id.decode()
                
                msg_data = await self.redis.xrange(
                    self.stream_name,
                    msg_id,
                    msg_id,
                    count=1
                )
                
                if not msg_data:
                    continue
                
                _, msg_fields = msg_data[0]
                for key, value in msg_fields.items():
                    key_str = key.decode() if isinstance(key, bytes) else key
                    value_str = value.decode() if isinstance(value, bytes) else value
                    
                    if key_str == "task_id" and int(value_str) == task_id:
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if task {task_id} is in stream: {str(e)}")
            return False
    
    async def _process_compensation_batch(self, task_ids: List[int]) -> int:
        """Process a batch of tasks to recover. Returns count of tasks needing recovery."""
        recovered_count = 0

        for task_id in task_ids:
            try:
                if await self._is_task_in_stream(task_id):
                    continue

                logger.warning(
                    f"Task {task_id} is PENDING in DB but not in Redis Stream, "
                    f"needs recovery (compensation callback should handle this)"
                )
                recovered_count += 1
                
            except Exception as e:
                logger.error(f"Error processing task {task_id} in compensation batch: {str(e)}")
                continue
        
        return recovered_count
    
    async def _compensation_loop_iteration(self):
        """Run one compensation iteration. Returns False if cancelled."""
        try:
            await asyncio.sleep(self.COMPENSATION_INTERVAL_SECONDS)
            pending_task_ids = await self._compensation_callback()
            if not pending_task_ids:
                return True
            recovered_count = await self._process_compensation_batch(pending_task_ids)
            
            if recovered_count > 0:
                logger.info(
                    f"Compensation scan found {recovered_count} tasks that need recovery"
                )
            
            return True
            
        except asyncio.CancelledError:
            logger.info("Compensation task cancelled")
            return False
        except Exception as e:
            logger.error(f"Error in compensation task: {str(e)}", exc_info=True)
            await asyncio.sleep(self.COMPENSATION_INTERVAL_SECONDS)
            return True
    
    async def start_compensation_task(self):
        """Start compensation task (background scan and recover lost tasks)."""
        if self._compensation_task and not self._compensation_task.done():
            logger.warning("Compensation task already running")
            return
        
        if not self._compensation_callback:
            logger.warning("No compensation callback registered, skipping compensation task")
            return
        
        async def compensation_loop():
            logger.info("Compensation task started")
            while True:
                should_continue = await self._compensation_loop_iteration()
                if not should_continue:
                    break
        
        self._compensation_task = asyncio.create_task(compensation_loop())
    
    async def stop_compensation_task(self):
        """Stop compensation task."""
        if self._compensation_task and not self._compensation_task.done():
            self._compensation_task.cancel()
            try:
                await self._compensation_task
            except asyncio.CancelledError:
                pass
            logger.info("Compensation task stopped")
    
    async def recover_pending_tasks(self, tasks: List[Any]) -> int:
        """Recover PENDING tasks from DB to Redis queue (e.g. after Redis restart). Returns count recovered."""
        if not tasks:
            logger.info("No pending tasks to recover")
            return 0
        
        recovered_count = 0
        skipped_count = 0
        
        logger.info(f"Starting recovery of {len(tasks)} pending tasks from database")
        
        for task in tasks:
            try:
                if await self._is_task_in_stream(task.id):
                    logger.debug(f"Task {task.id} already in stream, skipping")
                    skipped_count += 1
                    continue
                
                enqueued = await self.enqueue(
                    task_id=task.id,
                    task_type=task.task_type,
                    params=task.params if hasattr(task, 'params') and task.params else {},
                    user_id=task.user_id,
                    tenant_id=task.tenant_id
                )
                
                if enqueued:
                    recovered_count += 1
                    logger.info(f"Recovered task {task.id} (type: {task.task_type})")
                else:
                    skipped_count += 1
                    logger.warning(f"Failed to recover task {task.id}")
                    
            except Exception as e:
                logger.error(
                    f"Error recovering task {task.id}: {str(e)}",
                    exc_info=True
                )
                skipped_count += 1
        
        logger.info(
            f"Recovery completed: {recovered_count} tasks recovered, "
            f"{skipped_count} tasks skipped"
        )
        
        return recovered_count
    
    async def get_pending_messages(self, consumer_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pending messages (for monitoring)."""
        try:
            pending_info = await self.redis.xpending(
                self.stream_name,
                self.consumer_group
            )
            
            if pending_info[0] == 0:
                return []
            
            if consumer_name:
                pending_list = await self.redis.xpending_range(
                    self.stream_name,
                    self.consumer_group,
                    min="-",
                    max="+",
                    count=100,
                    consumername=consumer_name
                )
            else:
                pending_list = await self.redis.xpending_range(
                    self.stream_name,
                    self.consumer_group,
                    min="-",
                    max="+",
                    count=100
                )
            
            return [
                {
                    "message_id": (
                        msg["message_id"].decode()
                        if isinstance(msg["message_id"], bytes)
                        else msg["message_id"]
                    ),
                    "consumer": (
                        msg["consumer"].decode()
                        if isinstance(msg["consumer"], bytes)
                        else msg["consumer"]
                    ),
                    "time_since_delivered": msg["time_since_delivered"],
                    "delivery_count": msg["delivery_count"]
                }
                for msg in pending_list
            ]
            
        except Exception as e:
            logger.error(f"Failed to get pending messages: {str(e)}", exc_info=True)
            return []
    
    async def _get_pending_message_ids(self) -> set:
        """Get set of all pending message IDs."""
        try:
            all_pending = await self.redis.xpending_range(
                self.stream_name,
                self.consumer_group,
                min="-",
                max="+",
                count=10000
            )
            
            pending_ids = set()
            for msg in all_pending:
                msg_id = msg["message_id"]
                if isinstance(msg_id, bytes):
                    msg_id = msg_id.decode()
                pending_ids.add(msg_id)
            
            return pending_ids
            
        except Exception as e:
            logger.error(f"Failed to get pending message IDs: {str(e)}")
            return set()
    
    def _parse_message_timestamp(self, msg_id_str: str) -> Optional[int]:
        """Parse message ID to get timestamp (ms); returns None on failure."""
        try:
            timestamp_ms = int(msg_id_str.split("-")[0])
            return timestamp_ms
        except (ValueError, IndexError):
            return None
    
    async def _delete_old_messages_batch(
        self,
        messages: List[tuple],
        pending_message_ids: set,
        cutoff_ms: int
    ) -> int:
        """Delete a batch of old messages; protect pending. Returns count deleted."""
        deleted_count = 0

        for msg_id, msg_data in messages:
            msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
            if msg_id_str in pending_message_ids:
                continue
            timestamp_ms = self._parse_message_timestamp(msg_id_str)
            if timestamp_ms is None:
                continue
            
            if timestamp_ms < cutoff_ms:
                try:
                    await self.redis.xdel(self.stream_name, msg_id_str)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete message {msg_id_str}: {str(e)}")
                    continue
        
        return deleted_count
    
    async def cleanup_old_messages(
        self,
        max_age_seconds: int = 3600,
        keep_pending: bool = True
    ) -> int:
        """Clean old messages from stream. Returns count cleaned."""
        try:
            pending_message_ids = set()
            if keep_pending:
                pending_message_ids = await self._get_pending_message_ids()
            old_messages = await self.redis.xrange(
                self.stream_name,
                "-",
                "+",
                count=1000
            )
            
            if not old_messages:
                return 0
            cutoff_ms = int(
                (datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)).timestamp() * 1000
            )
            deleted_count = await self._delete_old_messages_batch(
                old_messages,
                pending_message_ids,
                cutoff_ms
            )
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old messages")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old messages: {str(e)}", exc_info=True)
            return 0
    
    async def close(self):
        """Close queue connection."""
        await self.stop_compensation_task()
        if self._own_redis and hasattr(self, 'redis'):
            await self.redis.close()
            logger.info("TaskQueue closed")
