"""
Simple test cases to verify test configuration.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_app_exists(client: AsyncClient):
    """Test that app exists."""
    # Simple health check
    assert client is not None

@pytest.mark.asyncio
async def test_database_session(async_session: AsyncSession):
    """Test that database session works."""
    assert async_session is not None
    # Run a simple query
    from sqlalchemy import text
    result = await async_session.execute(text("SELECT 1"))
    assert result.scalar() == 1

