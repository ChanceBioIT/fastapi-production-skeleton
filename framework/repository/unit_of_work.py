"""
Unit of Work: manages repositories and transaction boundaries.
"""

from typing import Optional
from sqlmodel.ext.asyncio.session import AsyncSession
from framework.database.manager import DatabaseManager


class UnitOfWork:
    """Manages related repositories with a shared session and transaction commit/rollback."""

    def __init__(self, session: Optional[AsyncSession] = None):
        """Initialize UnitOfWork; session must be provided (e.g. UnitOfWork.from_session())."""
        if session is None:
            raise ValueError("Session must be provided. Use UnitOfWork.from_session() or pass session explicitly.")
        
        self.session = session
        self._repositories = {}
    
    @classmethod
    async def from_session(cls, session: AsyncSession) -> "UnitOfWork":
        """Create UnitOfWork from an existing session."""
        return cls(session=session)

    def get_repository(self, repo_class, model_class):
        """Get or create a repository instance (cached)."""
        cache_key = f"{repo_class.__name__}_{model_class.__name__}"
        if cache_key not in self._repositories:
            self._repositories[cache_key] = repo_class(self.session)
        return self._repositories[cache_key]

    async def commit(self) -> None:
        """Commit all changes."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Rollback all changes."""
        await self.session.rollback()

    async def flush(self) -> None:
        """Flush session (e.g. to get auto-increment IDs)."""
        await self.session.flush()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()

