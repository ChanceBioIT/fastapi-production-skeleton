"""
Repository abstract base class and generic implementation.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Type, Any
from sqlmodel import SQLModel, select, col
from sqlmodel.ext.asyncio.session import AsyncSession

T = TypeVar("T", bound=SQLModel)


class IRepository(ABC, Generic[T]):
    """Repository interface; defines standard data access API."""

    @abstractmethod
    async def get_by_id(self, id: int) -> Optional[T]:
        """Get entity by ID."""
        pass

    @abstractmethod
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """Get all entities (paginated)."""
        pass

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create entity."""
        pass

    @abstractmethod
    async def update(self, entity: T) -> T:
        """Update entity."""
        pass

    @abstractmethod
    async def delete(self, id: int) -> bool:
        """Delete entity."""
        pass


class BaseRepository(IRepository[T]):
    """Generic repository implementation with SQLModel CRUD; subclasses can add custom queries."""

    def __init__(self, session: AsyncSession, model: Type[T]):
        """Initialize repository with session and model."""
        self.session = session
        self.model = model
    
    async def get_by_id(self, id: int) -> Optional[T]:
        """Get entity by ID."""
        statement = select(self.model).where(self.model.id == id)
        result = await self.session.exec(statement)
        return result.first()
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """Get all entities (paginated)."""
        statement = select(self.model).limit(limit).offset(offset)
        result = await self.session.exec(statement)
        return list(result.all())
    
    async def create(self, entity: T) -> T:
        """Create entity."""
        self.session.add(entity)
        return entity
    
    async def update(self, entity: T) -> T:
        """Update entity (SQLModel tracks changes)."""
        self.session.add(entity)
        return entity
    
    async def delete(self, id: int) -> bool:
        """Delete entity."""
        entity = await self.get_by_id(id)
        if entity:
            await self.session.delete(entity)
            return True
        return False
    
    async def find_one(self, **filters) -> Optional[T]:
        """Find one entity by filters (e.g. username='admin')."""
        statement = select(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                statement = statement.where(getattr(self.model, key) == value)
        
        result = await self.session.exec(statement)
        return result.first()
    
    async def find_all(self, **filters) -> List[T]:
        """Find entities by filters."""
        statement = select(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                statement = statement.where(getattr(self.model, key) == value)
        
        result = await self.session.exec(statement)
        return list(result.all())
    
    async def count(self, **filters) -> int:
        """Count entities matching filters."""
        from sqlmodel import func
        statement = select(func.count(self.model.id))
        for key, value in filters.items():
            if hasattr(self.model, key):
                statement = statement.where(getattr(self.model, key) == value)
        
        result = await self.session.exec(statement)
        return result.one()

