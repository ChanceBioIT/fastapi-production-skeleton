from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession
from .base import BaseDatabaseDriver

class MySQLDriver(BaseDatabaseDriver):
    def __init__(self, url: str):
        self.engine = create_async_engine(url, echo=False, future=True)
        self.session_factory = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def connect(self):
        """Connect to database (SQLModel engine manages connections)."""
        from sqlalchemy import text
        async with self.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))

    async def disconnect(self):
        """Disconnect from database."""
        await self.engine.dispose()

    async def get_session(self):
        async with self.session_factory() as session:
            yield session