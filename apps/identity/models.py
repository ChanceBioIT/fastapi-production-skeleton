from sqlmodel import SQLModel, Field, JSON, Column
from typing import Optional, Dict
from framework.config import settings

class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    # Quota config, e.g. {"max_tasks": 20, "max_storage_gb": 10}
    quotas: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    used_quotas: Dict = Field(default_factory=dict, sa_column=Column(JSON))

class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    hashed_password: str
    tenant_id: int = Field(foreign_key="tenants.id")
    role: str = Field(default="admin")  # admin, member