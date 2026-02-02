# Alembic Database Migrations

## Usage

### Initialize database (first run)

```bash
# Create database if needed
# MySQL: CREATE DATABASE app_db;  (or match DB_NAME in .env)

# Run migrations
alembic upgrade head
```

### Create new migration

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "description"

# Create empty migration
alembic revision -m "description"
```

### Apply migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade to specific revision
alembic upgrade <revision>

# Upgrade one step
alembic upgrade +1
```

### Rollback migrations

```bash
# Rollback one step
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision>

# Rollback all
alembic downgrade base
```

### View migration history

```bash
# Current version
alembic current

# History
alembic history

# Verbose history
alembic history --verbose
```

## Notes

1. **Database driver**: Alembic uses sync driver `pymysql`; the app uses async `aiomysql`.
2. **Model import**: Import all models to migrate in `apps/models.py`; `alembic/env.py` uses `import apps.models`.
3. **Environment**: DB config is read from `framework.config.settings` and `.env`.

## Migration layout

- `alembic/versions/` - migration files
- `alembic/env.py` - Alembic env config
- `alembic.ini` - main config

