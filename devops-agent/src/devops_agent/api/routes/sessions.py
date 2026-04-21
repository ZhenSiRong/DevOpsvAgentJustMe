"""
路由 5/7：会话管理

GET  /api/v1/sessions          — 列出所有会话（分页）
GET  /api/v1/sessions/{id}     — 获取单个会话详情（含完整消息历史）
DELETE /api/v1/sessions/{id}   — 归档/删除会话
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, HTTPException

from ..schemas import APIResponse, SessionSummary, SessionDetail, PaginatedData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["会话管理"])


@router.get("", response_model=APIResponse, summary="会话列表")
async def list_sessions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(None, description="active | archived"),
) -> APIResponse:
    """
    分页列出所有会话。

    返回每个会话的摘要信息：ID、创建时间、更新时间、消息数量。
    """
    # TODO: Day5 接入 DB 查询
    return APIResponse(
        data=PaginatedData[SessionSummary](
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
        ),
        message="会话列表功能待接入数据库",
    )


@router.get("/{session_id}", response_model=APIResponse, summary="会话详情")
async def get_session(session_id: str) -> APIResponse:
    """
    获取单个会话的完整详情。

    包括：
    - 会话元信息（创建时间/更新时间）
    - 完整消息历史（user + assistant 消息）
    - 工具调用统计（执行了几条命令、调用了几次探针）
    """
    # 验证 session_id 格式
    if not session_id or len(session_id) < 4:
        raise HTTPException(status_code=400, detail="无效的会话 ID")

    # TODO: Day5 接入 DB 查询
    # Mock: 返回空详情结构
    return APIResponse(
        data=SessionDetail(
            session_id=session_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            messages=[],
            execution_count=0,
            probe_call_count=0,
        ).model_dump(),
        message="会话详情功能待接入数据库",
    )


@router.delete("/{session_id}", response_model=APIResponse, description="归档会话")
async def archive_session(session_id: str) -> APIResponse:
    """
    归档一个会话（软删除，数据保留用于审计）。

    归档后的会话不再出现在活跃列表中，但可通过 audit 日志追溯。
    """
    # TODO: Day5 接入 DB 更新
    return APIResponse(
        data={"session_id": session_id, "archived": True},
        message=f"会话 {session_id} 已归档",
    )
