from loguru import logger
from framework.security import get_password_hash, verify_password
from framework.exceptions.handler import BusinessException
from framework.config import settings
from framework.repository.unit_of_work import UnitOfWork
from sqlalchemy.exc import IntegrityError
from .models import Tenant, User
from .repository import TenantRepository, UserRepository

class IdentityService:
    def __init__(self, uow: UnitOfWork):
        """Initialize Identity Service with UnitOfWork."""
        self.uow = uow

    async def register_tenant_admin(self, username: str, password: str, tenant_name: str):
        """Register new tenant and its admin."""
        tenant_repo = self.uow.get_repository(TenantRepository, Tenant)
        user_repo = self.uow.get_repository(UserRepository, User)
        
        existing_tenant = await tenant_repo.get_by_name(tenant_name)
        if existing_tenant:
            raise BusinessException("Tenant/org name already registered", code=400)

        try:
            new_tenant = Tenant(
                name=tenant_name,
                quotas={
                    "max_tasks": settings.DEFAULT_MAX_TASKS,
                    "max_storage_gb": settings.DEFAULT_STORAGE_GB,
                    "concurrent_limit": 2
                },
                used_quotas={
                    "tasks_count": 0,
                    "storage_gb": 0
                }
            )
            await tenant_repo.create(new_tenant)
            await self.uow.flush()
            new_user = User(
                username=username,
                hashed_password=get_password_hash(password),
                tenant_id=new_tenant.id,
                role="admin"
            )
            await user_repo.create(new_user)
            
            await self.uow.commit()
            logger.info(f"Tenant {tenant_name} created with admin {username}. Quotas initialized.")
            
            return new_user

        except BusinessException:
            await self.uow.rollback()
            raise
        except IntegrityError as e:
            await self.uow.rollback()
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            error_msg_lower = error_msg.lower()
            if any(keyword in error_msg_lower for keyword in [
                'username', 
                'users.username',
                'users_username',
                'duplicate entry',
                'unique constraint'
            ]):
                logger.warning(f"Username {username} already exists")
                raise BusinessException(
                    "Username already exists",
                    status_code=200,
                    code=4001
                )
            logger.error(f"Database integrity error: {error_msg}")
            raise BusinessException("Registration failed: data conflict", code=400)
        except Exception as e:
            await self.uow.rollback()
            logger.error(f"Failed to register tenant: {str(e)}")
            raise BusinessException("Registration failed: internal error", code=500)

    async def authenticate_user(self, username: str, password: str):
        """Authenticate user and return user info."""
        tenant_repo = self.uow.get_repository(TenantRepository, Tenant)
        user_repo = self.uow.get_repository(UserRepository, User)
        user = await user_repo.get_by_username(username)
        if not user:
            raise BusinessException("Invalid username or password", code=401)
        if not verify_password(password, user.hashed_password):
            raise BusinessException("Invalid username or password", code=401)
        tenant = await tenant_repo.get_by_id(user.tenant_id)
        if not tenant:
            raise BusinessException("User tenant not found", code=500)
        
        logger.info(f"User {username} authenticated successfully")
        return user