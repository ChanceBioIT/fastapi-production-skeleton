"""Test config and shared fixtures."""
import pytest
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from framework.security import CurrentUser
from apps.tasks.models import Task, TaskStatus
from apps.identity.models import Tenant, User


# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
def test_user() -> CurrentUser:
    """Create test user."""
    return CurrentUser(
        id=1,
        username="test_user",
        tenant_id=1,
        role="admin"
    )


@pytest.fixture(scope="function")
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Create async test database session."""
    # Import all models so they are registered in metadata
    from apps.tasks.models import Task
    from apps.identity.models import Tenant, User
    from sqlmodel import SQLModel
    
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def mock_db_session(async_session: AsyncSession) -> AsyncSession:
    """Return mock DB session."""
    return async_session


@pytest.fixture
def mock_current_user_dependency(test_user: CurrentUser):
    """Mock get_current_user dependency."""
    def _get_current_user():
        return test_user
    return _get_current_user


@pytest.fixture
def mock_db_dependency(mock_db_session: AsyncSession):
    """Mock get_db dependency."""
    def _get_db():
        yield mock_db_session
    return _get_db


@pytest.fixture
async def client(
    async_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Create test client."""
    # Override dependencies
    from apps.tasks.api.router import get_db
    from framework.security import get_current_user
    
    async def _get_db():
        yield async_session
    
    async def _get_current_user():
        from framework.security import CurrentUser
        return CurrentUser(
            id=1,
            username="test_user",
            tenant_id=1,
            role="admin"
        )
    
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_current_user
    
    # Use ASGITransport to test FastAPI app
    # httpx 0.24.0+ supports ASGITransport
    from httpx import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
async def sample_tenant(async_session: AsyncSession) -> Tenant:
    """Create sample tenant."""
    tenant = Tenant(
        id=1,
        name="test_tenant",
        quotas={"max_tasks": 20, "max_storage_gb": 10},
        used_quotas={"tasks_count": 0, "storage_gb": 0}
    )
    async_session.add(tenant)
    await async_session.commit()
    await async_session.refresh(tenant)
    return tenant


@pytest.fixture
async def sample_user(async_session: AsyncSession, sample_tenant: Tenant) -> User:
    """Create sample user."""
    user = User(
        id=1,
        username="test_user",
        hashed_password="hashed_password",
        tenant_id=sample_tenant.id,
        role="admin"
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def sample_task(
    async_session: AsyncSession,
    sample_user: User,
    sample_tenant: Tenant
) -> Task:
    """Create sample task."""
    task = Task(
        id=1,
        task_type="seq_toolkit",
        status=TaskStatus.COMPLETED,
        user_id=sample_user.id,
        tenant_id=sample_tenant.id,
        params={"sequence": "ATCG", "operation": "gc_content"},
        result={"gc_content": 50.0},
        is_sync=True
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    return task


@pytest.fixture(autouse=True)
async def cleanup_test_data(async_session: AsyncSession, request):
    """
    Fixture to auto-cleanup test data.
    
    Cleans test data after each test. Disable with pytest option --no-cleanup.
    
    Note: This fixture is for in-memory DB (test env) only; it does not affect production.
    """
    yield
    
    # Check if auto-cleanup is disabled
    if request.config.getoption("--no-cleanup", default=False):
        return
    
    # Clean all test data (in-memory DB only)
    try:
        from sqlmodel import delete
        
        # Delete all tasks
        delete_tasks = delete(Task)
        await async_session.execute(delete_tasks)
        
        # Delete all users
        delete_users = delete(User)
        await async_session.execute(delete_users)
        
        # Delete all tenants
        delete_tenants = delete(Tenant)
        await async_session.execute(delete_tenants)
        
        await async_session.commit()
    except Exception as e:
        await async_session.rollback()
        # In test env, cleanup failure should not fail the test
        print(f"Warning: Error during test data cleanup: {e}")


def pytest_addoption(parser):
    """Add pytest command-line options."""
    parser.addoption(
        "--clean-test-data",
        action="store_true",
        default=False,
        help="Explicitly clean test data (for standalone cleanup run)"
    )
    parser.addoption(
        "--no-cleanup",
        action="store_true",
        default=False,
        help="Disable auto-cleanup of test data"
    )


def pytest_configure(config):
    """Configure pytest."""
    # If --clean-test-data specified, run cleanup
    if config.getoption("--clean-test-data"):
        import asyncio
        import sys
        from framework.database.manager import DatabaseManager
        from framework.config import settings
        
        async def clean_all_test_data():
            """Clean all test data."""
            manager = DatabaseManager.get_instance()
            async for session in manager.mysql.get_session():
                try:
                    from sqlmodel import delete
                    from apps.tasks.models import Task
                    from apps.identity.models import User, Tenant
                    
                    print("=" * 60)
                    print("Starting test data cleanup...")
                    print(f"Database: {settings.DATABASE_URL}")
                    print("=" * 60)
                    
                    # Delete all tasks
                    delete_tasks = delete(Task)
                    result = await session.execute(delete_tasks)
                    task_count = result.rowcount
                    print(f"  ✓ Deleted {task_count} task(s)")
                    
                    # Delete all users
                    delete_users = delete(User)
                    result = await session.execute(delete_users)
                    user_count = result.rowcount
                    print(f"  ✓ Deleted {user_count} user(s)")
                    
                    # Delete all tenants
                    delete_tenants = delete(Tenant)
                    result = await session.execute(delete_tenants)
                    tenant_count = result.rowcount
                    print(f"  ✓ Deleted {tenant_count} tenant(s)")
                    
                    await session.commit()
                    print("=" * 60)
                    print("Test data cleanup completed.")
                    print("=" * 60)
                except Exception as e:
                    await session.rollback()
                    print(f"Test data cleanup failed: {e}")
                    sys.exit(1)
        
        # Run cleanup
        asyncio.run(clean_all_test_data())
        # Exit pytest without running tests
        sys.exit(0)