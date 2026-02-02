"""
Standalone test data cleanup script.

Usage:
    python -m tests.cleanup_test_data
    or
    pytest --clean-test-data
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from framework.database.manager import DatabaseManager
from framework.config import settings
from sqlmodel import delete
from apps.tasks.models import Task
from apps.identity.models import User, Tenant


async def clean_all_test_data():
    """Clean all test data. WARNING: removes all data from the database."""
    print("=" * 60)
    print("Test Data Cleanup Tool")
    print("=" * 60)
    print(f"Database: {settings.DATABASE_URL}")
    print()

    confirm = await asyncio.to_thread(
        input, "WARNING: This will delete all test data! Continue? (yes/no): "
    )
    if confirm.lower() != "yes":
        print("Cancelled")
        return

    manager = DatabaseManager.get_instance()
    try:
        async for session in manager.mysql.get_session():
            try:
                print("\nCleaning test data...")

                delete_tasks = delete(Task)
                result = await session.execute(delete_tasks)
                task_count = result.rowcount
                print(f"  Deleted {task_count} task(s)")

                delete_users = delete(User)
                result = await session.execute(delete_users)
                user_count = result.rowcount
                print(f"  Deleted {user_count} user(s)")

                delete_tenants = delete(Tenant)
                result = await session.execute(delete_tenants)
                tenant_count = result.rowcount
                print(f"  Deleted {tenant_count} tenant(s)")

                await session.commit()
                print("\nTest data cleanup completed.")

            except Exception as e:
                await session.rollback()
                print(f"\nCleanup failed: {e}")
                raise
    finally:
        try:
            await manager.mysql.disconnect()
        except Exception:
            pass


async def clean_test_data_by_pattern(pattern: str = "test"):
    """Clean test data matching pattern (e.g. records containing 'test')."""
    print("=" * 60)
    print(f"Cleaning test data matching '{pattern}'")
    print("=" * 60)
    print(f"Database: {settings.DATABASE_URL}")
    print()

    manager = DatabaseManager.get_instance()
    try:
        async for session in manager.mysql.get_session():
            try:
                print(f"\nCleaning test data matching '{pattern}'...")

                from sqlmodel import select
                like_pattern = f"%{pattern}%"
                tasks = (await session.exec(select(Task).where(Task.job_id.like(like_pattern)))).all()
                task_count = 0
                for t in tasks:
                    await session.delete(t)
                    task_count += 1
                print(f"  Deleted {task_count} matching task(s)")

                users = (await session.exec(select(User).where(User.username.like(like_pattern)))).all()
                user_count = 0
                for u in users:
                    await session.delete(u)
                    user_count += 1
                print(f"  Deleted {user_count} matching user(s)")

                tenants = (await session.exec(select(Tenant).where(Tenant.name.like(like_pattern)))).all()
                tenant_count = 0
                for t in tenants:
                    await session.delete(t)
                    tenant_count += 1
                print(f"  Deleted {tenant_count} matching tenant(s)")

                await session.commit()
                print(f"\nCleanup completed. Total deleted: {task_count + user_count + tenant_count}")

            except Exception as e:
                await session.rollback()
                print(f"\nCleanup failed: {e}")
                raise
    finally:
        try:
            await manager.mysql.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Clean test data")
    parser.add_argument("--pattern", type=str, help="Only delete records matching this pattern (e.g. 'test')")
    parser.add_argument("--all", action="store_true", help="Delete all data (dangerous!)")
    args = parser.parse_args()

    async def run():
        if args.all:
            await clean_all_test_data()
        elif args.pattern:
            await clean_test_data_by_pattern(args.pattern)
        else:
            print("Specify --pattern <pattern> or --all")
            print("\nExamples:")
            print("  python -m tests.cleanup_test_data --pattern test")
            print("  python -m tests.cleanup_test_data --all")

    try:
        asyncio.run(run())
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
