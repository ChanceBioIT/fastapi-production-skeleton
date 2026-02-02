"""
Model registration for migrations: import all models that should be migrated by Alembic here.
When adding/removing apps in a private project, add/remove the corresponding imports here; no need to change alembic/env.py.
"""
from apps.identity.models import Tenant, User
from apps.tasks.models import Task

__all__ = ["Tenant", "User", "Task"]
