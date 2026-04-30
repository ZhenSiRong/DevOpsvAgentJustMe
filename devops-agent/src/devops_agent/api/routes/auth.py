"""认证路由 — 登录 / 刷新 Token / 当前用户信息

端点：
- POST /api/v1/auth/login    用户登录，返回 JWT access_token
- POST /api/v1/auth/refresh  刷新 Token
- GET  /api/v1/auth/me       获取当前用户信息（需认证）
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .auth import (
    verify_login,
    create_access_token,
    get_current_user,
)
from ..api.schemas import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


# ============================================================
#  请求模型
# ============================================================

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT Access Token")
    token_type: str = Field("bearer", description="Token 类型")
    expires_in: int = Field(..., description="过期时间（秒）")


# ============================================================
#  端点
# ============================================================

@router.post("/login", response_model=APIResponse, summary="用户登录")
async def login(body: LoginRequest) -> APIResponse:
    """
    验证用户名密码，返回 JWT Access Token。

    成功返回 token，后续请求在 Authorization header 携带：
        Authorization: Bearer <access_token>
    """
    if not verify_login(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    from ..config import get_settings
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    token = create_access_token(
        data={"sub": body.username, "role": "admin"},
        expires_delta=expires_delta,
    )

    logger.info("用户登录成功: %s", body.username)

    return APIResponse(
        data={
            "access_token": token,
            "token_type": "bearer",
            "expires_in": int(expires_delta.total_seconds()),
        },
        message="登录成功",
    )


@router.post("/refresh", response_model=APIResponse, summary="刷新 Token")
async def refresh_token(
    current_user: dict = Depends(get_current_user),
) -> APIResponse:
    """使用当前有效 Token 换取新 Token（延长过期时间）。"""
    from ..config import get_settings
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    token = create_access_token(
        data={"sub": current_user["username"], "role": current_user["role"]},
        expires_delta=expires_delta,
    )

    return APIResponse(
        data={
            "access_token": token,
            "token_type": "bearer",
            "expires_in": int(expires_delta.total_seconds()),
        },
        message="Token 已刷新",
    )


@router.get("/me", response_model=APIResponse, summary="当前用户信息")
async def get_me(
    current_user: dict = Depends(get_current_user),
) -> APIResponse:
    """获取当前 Token 对应的用户信息。"""
    return APIResponse(data=current_user)


__all__ = ["router"]
