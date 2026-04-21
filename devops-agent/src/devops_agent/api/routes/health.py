"""
路由 1/7：健康检查 + 基础信息

GET /health — 应用存活探针（供 K8s liveness/readiness 使用）
GET /api/v1/info — 应用版本信息 + 模块状态
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ...db.connection import db_manager
from ...config import get_settings
from ..schemas import APIResponse, HealthStatus

router = APIRouter(tags=["健康检查"])

# 记录启动时间（用于计算 uptime）
_app_start_time = time.monotonic()


@router.get("/health", response_model=HealthStatus, summary="健康检查")
async def health_check() -> HealthStatus:
    """
    应用健康检查端点。

    返回服务状态、数据库连接状态、运行时长等信息。
    用于 Kubernetes livenessProbe / readinessProbe，以及负载均衡器健康检查。
    """
    settings = get_settings()
    
    # 检查 DB 连接
    db_ok = False
    try:
        conn = await db_manager.get_connection()
        if conn:
            await db_manager.release_connection(conn)
            db_ok = True
    except Exception:
        db_ok = False

    uptime = time.monotonic() - _app_start_time

    return HealthStatus(
        status="ok" if db_ok else "degraded",
        app=settings.app_name,
        version="0.1.0",
        db_connected=db_ok,
        uptime_seconds=round(uptime, 2),
    )


@router.get("/api/v1/info", response_model=APIResponse, summary="应用信息")
async def app_info() -> APIResponse:
    """返回应用版本、当前配置摘要、各模块就绪状态"""
    settings = get_settings()

    return APIResponse(
        data={
            "app": settings.app_name,
            "version": "0.1.0",
            "llm_protocol": settings.llm_protocol,
            "llm_model": settings.llm_model,
            "exec_user": settings.safe_exec_user,
            "modules": {
                "database": "connected" if await _check_db() else "disconnected",
                "safety_validator": "loaded",
                "probe": "loaded",
                "executor": "loaded",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def _check_db() -> bool:
    try:
        conn = await db_manager.get_connection()
        if conn:
            await db_manager.release_connection(conn)
            return True
    except Exception:
        pass
    return False
