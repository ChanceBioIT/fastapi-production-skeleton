"""
Multi-process Worker manager.
Starts and manages multiple Worker processes.
"""

import asyncio
import multiprocessing
import signal
import sys
import os
import time
import threading
from typing import List, Optional, Dict
from datetime import datetime, timezone
from framework.logging.logger import get_logger

logger = get_logger("worker_manager")


def run_worker_process(
    consumer_name: str,
    poll_interval: int = 1,
    worker_id: Optional[str] = None
):
    """
    Run a single Worker in a child process.
    
    Args:
        consumer_name: Worker consumer name
        poll_interval: Poll interval
        worker_id: Worker ID (string unique identifier for logging)
    """
    # Set process name
    if worker_id is not None:
        process_name = f"worker-{worker_id}"
        try:
            import setproctitle  # type: ignore  # Optional dependency, skip if not installed
            setproctitle.setproctitle(process_name)
        except ImportError:
            pass  # setproctitle optional, skip if not installed
    
    # Run worker in child process
    from apps.tasks.worker import TaskWorker
    from framework.logging.logger import LogConfig
    
    # If worker_id provided, set worker-specific log config
    if worker_id is not None:
        LogConfig.setup_worker_logging(worker_id)
    
    async def _run_worker():
        """Run worker in async context"""
        worker = TaskWorker(
            consumer_name=consumer_name,
            poll_interval=poll_interval,
            worker_id=worker_id
        )
        
        # Register signal handlers
        shutdown_task_ref = None
        
        def signal_handler(sig, frame):
            nonlocal shutdown_task_ref
            logger.info(f"Worker {consumer_name} received signal, initiating shutdown...")
            shutdown_task_ref = asyncio.create_task(worker.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            await worker.initialize()
            await worker.run()
        except KeyboardInterrupt:
            logger.info(f"Worker {consumer_name} interrupted")
        except Exception as e:
            logger.error(f"Worker {consumer_name} failed: {str(e)}", exc_info=True)
            sys.exit(1)
        finally:
            await worker.shutdown()
    
    # Run async worker
    try:
        asyncio.run(_run_worker())
    except KeyboardInterrupt:
        logger.info(f"Worker {consumer_name} interrupted")
    except Exception as e:
        logger.error(f"Worker {consumer_name} failed: {str(e)}", exc_info=True)
        sys.exit(1)


class WorkerManager:
    """Multi-process Worker manager (process monitoring and auto-restart)."""
    
    def __init__(
        self,
        num_workers: Optional[int] = None,
        poll_interval: int = 1,
        worker_name_prefix: str = "worker",
        monitor_interval: int = 30,
        restart_delay: int = 5,
        max_restarts: int = 10,
        restart_window: int = 3600
    ):
        """
        Initialize Worker manager.
        
        Args:
            num_workers: Number of Worker processes (None = CPU count)
            poll_interval: Poll interval per Worker
            worker_name_prefix: Worker name prefix
            monitor_interval: Monitor check interval (seconds)
            restart_delay: Wait time before restart (seconds)
            max_restarts: Max restarts within time window
            restart_window: Time window for restart count (seconds)
        """
        if num_workers is None:
            num_workers = multiprocessing.cpu_count()
        
        self.num_workers = num_workers
        self.poll_interval = poll_interval
        self.worker_name_prefix = worker_name_prefix
        self.monitor_interval = monitor_interval
        self.restart_delay = restart_delay
        self.max_restarts = max_restarts
        self.restart_window = restart_window
        
        self.processes: List[multiprocessing.Process] = []
        self.process_info: Dict[int, dict] = {}  # worker_id -> {process, restart_count, restart_times}
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()  # Protects process list
        
        # Set multiprocessing start method (Windows needs 'spawn', Linux can use 'fork')
        if sys.platform == 'win32':
            try:
                multiprocessing.set_start_method('spawn', force=True)
            except RuntimeError:
                pass  # Already set
        else:
            try:
                multiprocessing.set_start_method('fork', force=True)
            except RuntimeError:
                pass  # Already set
    
    def _create_process(self, worker_id: int) -> multiprocessing.Process:
        """
        Create Worker process object.
        
        Args:
            worker_id: Worker ID (integer, for internal management)
            
        Returns:
            Process object (not started)
        """
        consumer_name = f"{self.worker_name_prefix}-{worker_id}"
        # Convert integer worker_id to string unique identifier
        worker_id_str = f"{self.worker_name_prefix}-{worker_id}"
        
        return multiprocessing.Process(
            target=run_worker_process,
            args=(consumer_name, self.poll_interval, worker_id_str),
            name=consumer_name,
            daemon=False
        )
    
    def _update_process_info_for_restart(self, worker_id: int, process: multiprocessing.Process):
        """
        Update process info after restart.
        
        Args:
            worker_id: Worker ID
            process: New process object
        """
        old_process = self.process_info[worker_id]["process"]
        if old_process in self.processes:
            self.processes.remove(old_process)
        
        self.process_info[worker_id]["process"] = process
    
    def _create_new_process_info(self, worker_id: int, process: multiprocessing.Process):
        """
        Create new process info.
        
        Args:
            worker_id: Worker ID
            process: Process object
        """
        consumer_name = f"{self.worker_name_prefix}-{worker_id}"
        self.processes.append(process)
        self.process_info[worker_id] = {
            "process": process,
            "consumer_name": consumer_name,
            "restart_count": 0,
            "restart_times": [],
            "created_at": datetime.now(timezone.utc)
        }
    
    def _start_worker(self, worker_id: int, is_restart: bool = False) -> multiprocessing.Process:
        """
        Start a single Worker process.
        
        Args:
            worker_id: Worker ID
            is_restart: Whether this is a restart
            
        Returns:
            Started process object
        """
        consumer_name = f"{self.worker_name_prefix}-{worker_id}"
        process = self._create_process(worker_id)
        process.start()
        
        with self._lock:
            if is_restart and worker_id in self.process_info:
                self._update_process_info_for_restart(worker_id, process)
            else:
                self._create_new_process_info(worker_id, process)
        
        logger.info(
            f"Started worker process {worker_id}/{self.num_workers}: {consumer_name} "
            f"(PID: {process.pid})"
        )
        
        return process
    
    def start(self):
        """Start all Worker processes and begin monitoring."""
        self.running = True
        logger.info(f"Starting {self.num_workers} worker processes...")
        
        for i in range(1, self.num_workers + 1):
            self._start_worker(i)
            # Slight delay to avoid all processes starting at once
            time.sleep(0.1)
        
        logger.info(f"All {self.num_workers} worker processes started")
        
        # Start monitor thread
        self._start_monitor()
    
    def _should_restart(self, worker_id: int) -> bool:
        """
        Check whether the Worker should be restarted.
        
        Args:
            worker_id: Worker ID
            
        Returns:
            True if should restart, False otherwise
        """
        if worker_id not in self.process_info:
            return True
        
        info = self.process_info[worker_id]
        restart_times = info["restart_times"]
        
        # Remove restart records outside the time window
        now = datetime.now(timezone.utc)
        cutoff_time = now.timestamp() - self.restart_window
        restart_times[:] = [t for t in restart_times if t > cutoff_time]
        
        # Check if max restart count exceeded
        if len(restart_times) >= self.max_restarts:
            logger.error(
                f"Worker {info['consumer_name']} (ID: {worker_id}) has exceeded "
                f"maximum restart limit ({self.max_restarts} in {self.restart_window}s). "
                f"Will not restart automatically."
            )
            return False
        
        return True
    
    def _cleanup_old_process(self, process: multiprocessing.Process):
        """
        Clean up old process.
        
        Args:
            process: Process object to clean up
        """
        if not process.is_alive():
            return
        
        try:
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join()
        except Exception as e:
            logger.error(f"Error cleaning up old process: {str(e)}")
    
    def _update_restart_statistics(self, worker_id: int):
        """
        Update restart statistics.
        
        Args:
            worker_id: Worker ID
        """
        info = self.process_info[worker_id]
        info["restart_count"] += 1
        info["restart_times"].append(datetime.now(timezone.utc).timestamp())
    
    def _restart_worker(self, worker_id: int):
        """
        Restart a single Worker process.
        
        Args:
            worker_id: Worker ID
        """
        if worker_id not in self.process_info:
            logger.warning(f"Cannot restart worker {worker_id}: info not found")
            return
        
        info = self.process_info[worker_id]
        old_process = info["process"]
        consumer_name = info["consumer_name"]
        
        if not self._should_restart(worker_id):
            logger.warning(
                f"Worker {consumer_name} (ID: {worker_id}) will not be restarted "
                f"due to restart limit"
            )
            return
        
        self._cleanup_old_process(old_process)
        
        logger.info(
            f"Waiting {self.restart_delay} seconds before restarting "
            f"worker {consumer_name} (ID: {worker_id})..."
        )
        time.sleep(self.restart_delay)
        
        self._update_restart_statistics(worker_id)
        
        logger.info(
            f"Restarting worker {consumer_name} (ID: {worker_id}) "
            f"(restart #{info['restart_count']})..."
        )
        
        new_process = self._start_worker(worker_id, is_restart=True)
        
        logger.info(
            f"Worker {consumer_name} (ID: {worker_id}) restarted successfully "
            f"(new PID: {new_process.pid})"
        )
    
    def _check_process_exit_code(self, exitcode: Optional[int], worker_id: int, consumer_name: str) -> bool:
        """
        Check process exit code to decide whether to restart.
        
        Args:
            exitcode: Process exit code
            worker_id: Worker ID
            consumer_name: Worker name
            
        Returns:
            True if restart needed, False otherwise
        """
        if exitcode is None:
            # Process still running but is_alive() returned False
            # Should not happen; continue monitoring for safety
            return False
        
        if exitcode == 0:
            logger.info(
                f"Worker {consumer_name} (ID: {worker_id}) "
                f"exited normally (exit code: 0)"
            )
            return False
        
        logger.warning(
            f"Worker {consumer_name} (ID: {worker_id}) "
            f"died unexpectedly (exit code: {exitcode})"
        )
        return True
    
    def _find_dead_processes(self) -> List[int]:
        """
        Find all dead processes.
        
        Returns:
            List of Worker IDs that need restart
        """
        processes_to_restart = []
        
        with self._lock:
            for worker_id, info in self.process_info.items():
                process = info["process"]
                consumer_name = info["consumer_name"]
                
                if not process.is_alive():
                    exitcode = process.exitcode
                    if self._check_process_exit_code(exitcode, worker_id, consumer_name):
                        processes_to_restart.append(worker_id)
        
        return processes_to_restart
    
    def _monitor_loop(self):
        """Monitor loop (runs in a separate thread)."""
        logger.info(f"Monitor loop started (check interval: {self.monitor_interval}s)")
        
        while self.running:
            try:
                time.sleep(self.monitor_interval)
                
                if not self.running:
                    break
                
                processes_to_restart = self._find_dead_processes()
                
                for worker_id in processes_to_restart:
                    if self.running:
                        self._restart_worker(worker_id)
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {str(e)}", exc_info=True)
                time.sleep(self.monitor_interval)
        
        logger.info("Monitor loop stopped")
    
    def _start_monitor(self):
        """Start monitor thread."""
        if self.monitor_thread is not None and self.monitor_thread.is_alive():
            logger.warning("Monitor thread already running")
            return
        
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="WorkerMonitor",
            daemon=False
        )
        self.monitor_thread.start()
        logger.info("Monitor thread started")
    
    def wait(self):
        """Wait for all Worker processes to finish."""
        try:
            # Wait for monitor thread and all processes
            if self.monitor_thread:
                self.monitor_thread.join()
            
            # Wait for all processes
            with self._lock:
                for process in self.processes:
                    process.join()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down workers...")
            self.shutdown()
    
    def _wait_for_monitor_thread(self):
        """Wait for monitor thread to finish."""
        if self.monitor_thread and self.monitor_thread.is_alive():
            logger.info("Waiting for monitor thread to stop...")
            self.monitor_thread.join(timeout=5)
    
    def _terminate_all_processes(self):
        """Terminate all processes."""
        with self._lock:
            for process in self.processes:
                if process.is_alive():
                    try:
                        process.terminate()
                        logger.info(
                            f"Sent TERM signal to worker {process.name} "
                            f"(PID: {process.pid})"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to terminate worker {process.name}: {str(e)}"
                        )
    
    def _wait_for_processes_exit(self, timeout: int):
        """
        Wait for all processes to exit.
        
        Args:
            timeout: Timeout in seconds
        """
        with self._lock:
            for process in self.processes:
                if process.is_alive():
                    try:
                        process.join(timeout=timeout)
                        if process.is_alive():
                            logger.warning(
                                f"Worker {process.name} (PID: {process.pid}) "
                                f"did not exit gracefully, forcing termination..."
                            )
                            process.kill()
                            process.join()
                    except Exception as e:
                        logger.error(
                            f"Error waiting for worker {process.name}: {str(e)}"
                        )
    
    def shutdown(self, timeout: int = 10):
        """
        Shut down all Worker processes.
        
        Args:
            timeout: Timeout in seconds to wait for process exit
        """
        self.running = False
        logger.info("Shutting down all worker processes...")
        
        self._wait_for_monitor_thread()
        self._terminate_all_processes()
        self._wait_for_processes_exit(timeout)
        
        logger.info("All worker processes shut down")
    
    def _calculate_recent_restarts(self, restart_times: List[float]) -> int:
        """
        Count restarts within the time window.
        
        Args:
            restart_times: List of restart timestamps
            
        Returns:
            Recent restart count
        """
        now = datetime.now(timezone.utc).timestamp()
        cutoff_time = now - self.restart_window
        return sum(1 for t in restart_times if t > cutoff_time)
    
    def _build_worker_health_info(self, worker_id: int, info: dict, process: multiprocessing.Process) -> dict:
        """
        Build health info for a single Worker.
        
        Args:
            worker_id: Worker ID
            info: Process info dict
            process: Process object
            
        Returns:
            Worker health info dict
        """
        is_alive = process.is_alive()
        recent_restarts = self._calculate_recent_restarts(info["restart_times"])
        
        return {
            "worker_id": worker_id,
            "name": info["consumer_name"],
            "pid": process.pid,
            "alive": is_alive,
            "exitcode": process.exitcode,
            "restart_count": info["restart_count"],
            "recent_restarts": recent_restarts,
            "created_at": info["created_at"].isoformat()
        }
    
    def _build_restart_stats(self, info: dict) -> dict:
        """
        Build restart statistics.
        
        Args:
            info: Process info dict
            
        Returns:
            Restart stats dict
        """
        recent_restarts = self._calculate_recent_restarts(info["restart_times"])
        
        return {
            "total_restarts": info["restart_count"],
            "recent_restarts": recent_restarts,
            "restart_times": [
                datetime.fromtimestamp(t, timezone.utc).isoformat()
                for t in info["restart_times"][-10:]
            ]
        }
    
    def check_health(self) -> dict:
        """
        Check health of all Worker processes.
        
        Returns:
            Dict with status for each Worker
        """
        health = {
            "total": 0,
            "alive": 0,
            "dead": 0,
            "workers": [],
            "restart_stats": {}
        }
        
        with self._lock:
            health["total"] = len(self.processes)
            
            for worker_id, info in self.process_info.items():
                process = info["process"]
                is_alive = process.is_alive()
                
                if is_alive:
                    health["alive"] += 1
                else:
                    health["dead"] += 1
                
                worker_info = self._build_worker_health_info(worker_id, info, process)
                health["workers"].append(worker_info)
                health["restart_stats"][worker_id] = self._build_restart_stats(info)
        
        return health


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Multi-process Worker Manager")
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker processes (default: CPU count)"
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=1,
        help="Poll interval in seconds for each worker"
    )
    parser.add_argument(
        "--worker-name-prefix",
        type=str,
        default="worker",
        help="Prefix for worker consumer names"
    )
    parser.add_argument(
        "--monitor-interval",
        type=int,
        default=30,
        help="Monitor check interval in seconds (default: 30)"
    )
    parser.add_argument(
        "--restart-delay",
        type=int,
        default=5,
        help="Delay before restarting a dead worker in seconds (default: 5)"
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=10,
        help="Maximum number of restarts per worker in the time window (default: 10)"
    )
    parser.add_argument(
        "--restart-window",
        type=int,
        default=3600,
        help="Time window for restart counting in seconds (default: 3600)"
    )
    
    args = parser.parse_args()
    
    manager = WorkerManager(
        num_workers=args.workers,
        poll_interval=args.poll_interval,
        worker_name_prefix=args.worker_name_prefix,
        monitor_interval=args.monitor_interval,
        restart_delay=args.restart_delay,
        max_restarts=args.max_restarts,
        restart_window=args.restart_window
    )
    
    # Register signal handlers
    def signal_handler(sig, frame):
        logger.info("Received signal, shutting down...")
        manager.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start all workers
        manager.start()
        
        # Wait for all workers to exit
        manager.wait()
        
    except Exception as e:
        logger.error(f"Worker manager failed: {str(e)}", exc_info=True)
        manager.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()

