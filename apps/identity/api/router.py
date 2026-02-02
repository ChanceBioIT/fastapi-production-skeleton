from fastapi import APIRouter, Depends, Response
from sqlmodel.ext.asyncio.session import AsyncSession
from framework.database.manager import DatabaseManager
from framework.repository.unit_of_work import UnitOfWork
from framework.response import ResponseModel
from framework.security import create_access_token
from framework.config import settings
from ..service import IdentityService
from pydantic import BaseModel
from datetime import timedelta

router = APIRouter()

class RegisterSchema(BaseModel):
    username: str
    password: str
    tenant_name: str

class LoginSchema(BaseModel):
    username: str
    password: str

async def get_db():
    manager = DatabaseManager.get_instance()
    async for session in manager.mysql.get_session():
        yield session

def get_uow(
    db: AsyncSession = Depends(get_db)
) -> UnitOfWork:
    """Dependency: create UnitOfWork."""
    return UnitOfWork(session=db)

def get_identity_service(uow: UnitOfWork = Depends(get_uow)) -> IdentityService:
    """Dependency: create IdentityService."""
    return IdentityService(uow)

@router.post("/register")
async def register(
    data: RegisterSchema, 
    service: IdentityService = Depends(get_identity_service)
):
    """Register new tenant and its admin."""
    user = await service.register_tenant_admin(
        data.username, data.password, data.tenant_name
    )
    return ResponseModel.success(data={"username": user.username, "tenant_id": user.tenant_id})

@router.post("/login")
async def login(
    data: LoginSchema, 
    response: Response,
    service: IdentityService = Depends(get_identity_service)
):
    """Login: return JWT and set cookie."""
    user = await service.authenticate_user(data.username, data.password)
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role
        },
        expires_delta=expires_delta
    )
    
    cookie_name = settings.ACCESS_TOKEN_COOKIE_NAME
    cookie_max_age = int(expires_delta.total_seconds())
    response.set_cookie(
        key=cookie_name,
        value=access_token,
        max_age=cookie_max_age,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE
    )
    
    return ResponseModel.success(
        data={
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "tenant_id": user.tenant_id,
                "role": user.role
            }
        }
    )

@router.post("/logout")
async def logout(response: Response):
    """Logout: clear token cookie."""
    cookie_name = settings.ACCESS_TOKEN_COOKIE_NAME
    response.delete_cookie(
        key=cookie_name,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE
    )
    return ResponseModel.success(data={"message": "Logged out successfully"})