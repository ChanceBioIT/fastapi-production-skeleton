"""Identity module repository implementations."""

from typing import Optional
from framework.repository.base import BaseRepository
from .models import Tenant, User


class TenantRepository(BaseRepository[Tenant]):
    """Tenant repository."""

    def __init__(self, session):
        super().__init__(session, Tenant)

    async def get_by_name(self, name: str) -> Optional[Tenant]:
        """Find tenant by name."""
        return await self.find_one(name=name)


class UserRepository(BaseRepository[User]):
    """User repository."""

    def __init__(self, session):
        super().__init__(session, User)

    async def get_by_username(self, username: str) -> Optional[User]:
        """Find user by username."""
        return await self.find_one(username=username)

    async def get_by_tenant_id(self, tenant_id: int) -> list[User]:
        """Find all users by tenant ID."""
        return await self.find_all(tenant_id=tenant_id)

