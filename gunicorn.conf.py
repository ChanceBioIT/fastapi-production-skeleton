"""
Gunicorn configuration file for production deployment.
"""
import multiprocessing
import os
from pathlib import Path

# Load LOG_DIR from .env (via framework.config)
from framework.config import settings

LOG_DIR = Path(settings.LOG_DIR)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Server
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = 2 
worker_class = "uvicorn.workers.UvicornWorker"  # Uvicorn worker for async support
worker_connections = 1000
max_requests = 1000  # Restart worker after this many requests to avoid memory leaks
max_requests_jitter = 50  # Jitter to avoid all workers restarting at once
timeout = 120  # Worker timeout (seconds)
keepalive = 5  # Keep-alive connection time (seconds)

# Process name (from config; fallback to APP_NAME)
proc_name = (settings.GUNICORN_PROC_NAME or settings.APP_NAME.lower().replace(" ", "-"))[:32]

# Logging (paths built from LOG_DIR in .env)
accesslog = str(LOG_DIR / "gunicorn_access.log")
errorlog = str(LOG_DIR / "gunicorn_error.log")
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process management
daemon = False  # Managed by systemd, do not daemonize
pidfile = str(LOG_DIR / "gunicorn.pid")
user = None  # User set by systemd
group = None  # Group set by systemd
umask = 0o007  # File permission mask

# Performance
preload_app = True  # Preload app to reduce memory usage
worker_tmp_dir = "/dev/shm"  # Use tmpfs if available for better performance

# Graceful restart
graceful_timeout = 30  # Graceful shutdown timeout

# Security
limit_request_line = 4094  # Max request line length
limit_request_fields = 100  # Max number of request headers
limit_request_field_size = 8190  # Max size of a single header

# Environment variables
raw_env = [
    # Add env vars here if needed
    # "APP_ENV=production",
]

def when_ready(server):
    """Callback when server is ready."""
    server.log.info("%s is ready. Listening on %s", settings.APP_NAME, server.address)

def on_exit(server):
    """Callback when server exits."""
    server.log.info("%s is shutting down.", settings.APP_NAME)

def worker_int(worker):
    """Callback when worker receives INT signal."""
    worker.log.info("Worker received INT signal")

def pre_fork(server, worker):
    """Callback before forking worker."""
    pass

def post_fork(server, worker):
    """Callback after forking worker."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_exec(server):
    """Callback before exec."""
    server.log.info("Forked child, re-executing.")

def worker_abort(worker):
    """Callback when worker aborts."""
    worker.log.info("Worker received SIGABRT signal")
