from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from framework.config import settings

# 1. Password hashing (BCrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 2. OAuth2 scheme and token URL (optional, for backward compatibility)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# --- Core models ---

# class TokenPayload(BaseModel):
#     """JWT payload"""
#     sub: Optional[str] = None      # User ID or username
#     tenant_id: Optional[int] = None # Tenant ID encoded in token
#     exp: Optional[int] = None

class CurrentUser(BaseModel):
    """Current logged-in user context"""
    id: int
    username: str
    tenant_id: int
    role: str

# --- Helpers ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt

# --- FastAPI dependencies ---

def get_token_from_request(
    request: Request,
    token_from_header: Optional[str] = Depends(oauth2_scheme)
) -> Optional[str]:
    """
    Get token from request: prefer cookie, then Authorization header.
    """
    cookie_name = settings.ACCESS_TOKEN_COOKIE_NAME
    token = request.cookies.get(cookie_name)
    
    if not token and token_from_header:
        token = token_from_header
    
    return token

def get_current_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request)
) -> CurrentUser:
    """
    Dependency: validate token and extract user. Use in router as user: CurrentUser = Depends(get_current_user).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise credentials_exception
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        tenant_id: int = payload.get("tenant_id")
        user_id: int = payload.get("user_id")
        role: str = payload.get("role")
        
        if username is None or tenant_id is None:
            raise credentials_exception
        
        if user_id is None:
            raise credentials_exception
        if role is None:
            role = "member"
            
        return CurrentUser(
            id=user_id,
            username=username,
            tenant_id=tenant_id,
            role=role
        )
    except JWTError:
        cookie_name = settings.ACCESS_TOKEN_COOKIE_NAME
        if request.cookies.get(cookie_name):
            pass  # Cookie cleanup handled in middleware or exception handler
        raise credentials_exception
    except Exception:
        raise credentials_exception