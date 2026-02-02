# FastAPI Production Skeleton

Production-ready FastAPI skeleton: multi-tenant, JWT auth, async task queue, and plugin-based task execution. Others can build full FastAPI applications on top of this skeleton.

## Quick Start

1. Clone or copy this repository.
2. Copy `.env.example` to `.env`, and at minimum update `SECRET_KEY`, `DB_*`, `REDIS_*` (if using task queue), and `APP_NAME`.
3. Install dependencies: `poetry install` (or `pip install -e .`).
4. Start MySQL and Redis (e.g. with Docker: `docker-compose up -d mysql redis`).
5. Run migrations: `alembic upgrade head`.
6. Start the app: `uvicorn main:app --reload` or `python main.py`.
7. Open `http://localhost:8000/docs` to view API documentation.

## Configuration

All configuration is overridden via environment variables or `.env`; defaults are in `framework/config.py`.

- **Required**: `SECRET_KEY`, `DB_*`, `APP_NAME` (for production).
- **Optional**: `API_V1_AUTH_PREFIX`, `API_V1_TASKS_PREFIX`, `TASK_QUEUE_STREAM_NAME`, `TASK_QUEUE_CONSUMER_GROUP`, etc.

See [docs/01_CONFIGURATION.md](docs/01_CONFIGURATION.md) for details.

## Adding a new app or plugin

- **New business app**: Create a subpackage under `apps/` (e.g. `apps/my_app`) with `models.py`, `api/router.py`, etc.; mount the router in `main.py` via `include_router`; import the new app's models in **`apps/models.py`** so Alembic migrations include the new tables.
- **New task plugin**: Implement `TaskPlugin` under `apps/tasks/plugins/` (see `base.py`), and register it in `task_registry` in `plugins/__init__.py`. Example plugin `seq_tool` can be removed or replaced.

## Deployment

- **Docker**: Use the root `docker-compose.yml`; pass config via environment or `.env`; container/network names can be renamed per project.
- **Systemd**: Copy `fastapi-app.service` and `fastapi-worker.service`, replace placeholders such as `WorkingDirectory`, `User`, and `SyslogIdentifier` with your project path and name, then install into systemd.

See the "Private project configuration guide" in [docs/01_CONFIGURATION.md](docs/01_CONFIGURATION.md).
