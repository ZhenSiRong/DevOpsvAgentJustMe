"""
路由 6/7：操作审计追踪

GET /api/v1/audit — 查询命令执行审计日志
GET /api/v1/audit/stats — 审计统计

审计是安全合规的核心组件：
- 记录每一次命令执行的完整上下文
- 支持按时间范围、执行状态、执行用户过滤
- 数据不可篡改（append-only）
- 用于事后追溯和安全事件分析
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, HTTPException

from ..schemas import APIResponse, AuditLogItem, PaginatedData
from ...db import query_audit_logs, get_audit_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audit", tags=["审计日志"])


@router.get("", response_model=APIResponse, summary="审计日志查询")
async def query_audit_logs_route(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(
        None,
        description="过滤: SUCCESS | FAILED | TIMEOUT | REJECTED | BLOCKED",
    ),
    start_time: str | None = Query(None, description="起始时间 ISO 8601"),
    end_time: str | None = Query(None, description="结束时间 ISO 8601"),
) -> APIResponse:
    if start_time:
        try:
            datetime.fromisoformat(start_time)
        except ValueError:
            raise HTTPException(status_code=422, detail="start_time 格式错误，需 ISO 8601")
    if end_time:
        try:
            datetime.fromisoformat(end_time)
        except ValueError:
            raise HTTPException(status_code=422, detail="end_time 格式错误，需 ISO 8601")

    valid_statuses = {"SUCCESS", "FAILED", "TIMEOUT", "REJECTED", "BLOCKED"}
    if status and status.upper() not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"无效的状态值: {status}，可选: {valid_statuses}",
        )

    logs, total = await query_audit_logs(
        page=page,
        page_size=page_size,
        status=status,
        start_time=start_time,
        end_time=end_time,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    items = [
        AuditLogItem(
            id=log.id,
            timestamp=log.timestamp,
            command=log.content[:200] if log.content else "",
            status=log.status.upper(),
            execution_time_ms=log.duration_ms,
            security_result=log.security_result,
        )
        for log in logs
    ]

    return APIResponse(
        data=PaginatedData[AuditLogItem](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
        message="ok",
    )


@router.get("/stats", response_model=APIResponse, summary="审计统计")
async def audit_stats_route() -> APIResponse:
    stats = await get_audit_stats()
    return APIResponse(data=stats, message="ok")
