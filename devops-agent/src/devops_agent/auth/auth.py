"""认证模块 — JWT Token 生成与验证

使用 HS256 算法，配置来自 Settings（.env / config.py）。

API：
- create_access_token(data, expire_minutes) → str
- verify_access_token(token) → dict | None
- get_current_user(token) → dict（FastAPI 依赖注入用）
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from ..config import get_settings

logger = logging.getLogger(__name__)

# ============================================================
#  默认管理员账号（生产环境应通过环境变量覆盖）
# ============================================================

_DEFAULT_ADMIN_USERNAME = "admin"
_DEFAULT_ADMIN_PASSWORD = "devops2024"  # ⚠️ 生产环境必须修改


def _get_admin_credentials() -> tuple[str, str]:
    import os
    username = os.environ.get("ADMIN_USERNAME", _DEFAULT_ADMIN_USERNAME)
    password = os.environ.get("ADMIN_PASSWORD", _DEFAULT_ADMIN_PASSWORD)
    return username, password


# ============================================================
#  Token 操作
# ============================================================

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """创建 JWT Access Token"""
    settings = get_settings()
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)

    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_access_token(token: str) -> dict | None:
    """验证 JWT Token，返回 payload 或 None"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None


# ============================================================
#  登录校验
# ============================================================

def verify_login(username: str, password: str) -> bool:
    """验证用户名和密码"""
    admin_user, admin_pass = _get_admin_credentials()
    return username == admin_user and password == admin_pass


# ============================================================
#  FastAPI 依赖注入：从请求头中解析当前用户
# ============================================================

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> dict:
    """
    FastAPI 依赖注入函数。
    从 Authorization: Bearer <token> 中解析当前用户。

    使用方式：
        @router.get("/secret")
        async def protected_route(user: dict = Depends(get_current_user)):
            ...
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = verify_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "username": payload.get("sub", "unknown"),
        "role": payload.get("role", "viewer"),
    }


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> dict | None:
    """
    可选认证：有 token 则解析，无 token 返回 None（不拦截）。
    用于需要区分登录/未登录状态的接口。
    """
    if credentials is None:
        return None
    token = credentials.credentials
    payload = verify_access_token(token)
    if payload is None:
        return None
    return {
        "username": payload.get("sub", "unknown"),
        "role": payload.get("role", "viewer"),
    }


__all__ = [
    "create_access_token",
    "verify_access_token",
    "verify_login",
    "get_current_user",
    "get_current_user_optional",
]
