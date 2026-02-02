# Configuration

This document describes how FastAPI Production Skeleton is configured and key points when building private projects on top of it.

## 1. Configuration sources

- **Environment variables**: Highest priority; set in shell or `.env`.
- **.env file**: In project root; loaded automatically by `framework.config.Settings` (Pydantic Settings).
- **Defaults**: In `framework/config.py` in the `Settings` class.

Env keys and `.env` keys match `Settings` attribute names (case-insensitive).

## 2. Main configuration

| Category | Variable | Description | Default |
|----------|----------|-------------|---------|
| App | APP_NAME | Display name (docs, email, logs) | FastAPI App |
| App | APP_DESCRIPTION | OpenAPI description | Production-ready FastAPI... |
| App | APP_VERSION | Version | 1.0.0 |
| App | APP_ENV | Environment | development |
| App | DEBUG | Debug mode | true |
| Security | SECRET_KEY | JWT key; must change in production | your-super-secret-key-... |
| Database | DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME | MySQL connection | localhost, 3306, root, root, app_db |
| Redis | REDIS_HOST, REDIS_PORT, REDIS_DB | Redis connection | localhost, 6379, 0 |
| Task queue | TASK_QUEUE_STREAM_NAME | Redis Stream name | tasks:queue |
| Task queue | TASK_QUEUE_CONSUMER_GROUP | Consumer group | tasks:workers |
| API | API_V1_AUTH_PREFIX | Auth route prefix | /api/v1/auth |
| API | API_V1_TASKS_PREFIX | Tasks route prefix | /api/v1/tasks |
| Log/Storage | LOG_DIR, JOB_WORKSPACE | Log dir, job workspace | logs, job_workspace |
| Gunicorn | GUNICORN_PROC_NAME | Process name; empty = from APP_NAME | (empty) |

See `framework/config.py` for more.

## 3. Private project configuration guide

When building a private project from this skeleton:

1. After copying the repo, copy `.env.example` to `.env`.
2. **Required**:
   - `SECRET_KEY`: Use a strong random key in production.
   - `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: Match your MySQL instance.
   - If using async tasks: set `REDIS_HOST` etc. to match your Redis.
   - `APP_NAME`: Your product/project name (Swagger title, email subject, Gunicorn logs, etc.).
3. **Optional**:
   - Change `API_V1_AUTH_PREFIX`, `API_V1_TASKS_PREFIX` to change API path prefixes.
   - Change `TASK_QUEUE_STREAM_NAME`, `TASK_QUEUE_CONSUMER_GROUP` when sharing Redis across projects.
   - Add a custom config module (e.g. extending `framework.config.Settings`) at project root and load it in `main.py` to add more options.
4. **Deployment**:
   - **Docker**: Use root `docker-compose.yml`; pass variables via environment or `.env`. Container/network names (e.g. fastapi-mysql, fastapi-web) can be renamed per project.
   - **Systemd**: Copy `fastapi-app.service` and `fastapi-worker.service`, replace placeholders such as `WorkingDirectory`, `User`, `ReadWritePaths`, `SyslogIdentifier` (e.g. `/var/www/your-app/current`) with your paths and names, then install into systemd.

## 4. Extending configuration

To add project-specific options:

- Add variables to `.env` and corresponding attributes to `Settings` in `framework/config.py` (single source of truth); or
- Create `config_overrides.py`, define a subclass of `framework.config.Settings` with new fields, and assign an instance to `framework.config.settings` at startup (before first use).

This keeps skeleton defaults while allowing env vars and optional overrides for your project.
