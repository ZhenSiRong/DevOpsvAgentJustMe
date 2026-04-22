"""
路由 5/7：会话管理

GET  /api/v1/sessions          — 列出所有会话（分页）
GET  /api/v1/sessions/{id}     — 获取单个会话详情（含完整消息历史）
DELETE /api/v1/sessions/{id}   — 归档/删除会话
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from ..schemas import APIResponse, SessionSummary, SessionDetail, PaginatedData
from ...db import (
    get_session,
    list_sessions,
    create_session,
    delete_session,
    get_messages_by_session,
    count_messages_by_session,
    get_audit_logs_by_session,
)


class SessionCreateRequest(BaseModel):
    title: str = Field(default="新对话", max_length=200)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["会话管理"])


@router.post("", response_model=APIResponse, summary="创建会话")
async def create_session_route(body: SessionCreateRequest) -> APIResponse:
    session = await create_session(title=body.title)
    return APIResponse(
        data={
            "session_id": session.id,
            "title": session.title,
            "created_at": session.created_at,
        },
        message="会话创建成功",
    )


@router.get("", response_model=APIResponse, summary="会话列表")
async def list_sessions_route(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> APIResponse:
    sessions, total = await list_sessions(page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    items = [
        SessionSummary(
            session_id=s.id,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=0,  # TODO: 批量 count 性能优化
            title=s.title,
        )
        for s in sessions
    ]

    return APIResponse(
        data=PaginatedData[SessionSummary](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
        message="ok",
    )


@router.get("/{session_id}", response_model=APIResponse, summary="会话详情")
async def get_session_route(session_id: str) -> APIResponse:
    if not session_id or len(session_id) < 4:
        raise HTTPException(status_code=400, detail="无效的会话 ID")

    session = await get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")

    # 消息历史
    messages, _ = await get_messages_by_session(session_id, page=1, page_size=1000)
    msg_count = await count_messages_by_session(session_id)

    # 审计日志统计
    audit_logs = await get_audit_logs_by_session(session_id)
    exec_count = sum(1 for a in audit_logs if a.phase == "execution")
    probe_count = sum(1 for a in audit_logs if a.phase in ("received", "sense"))

    return APIResponse(
        data=SessionDetail(
            session_id=session.id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[
                {
                    "role": m.role,
                    "content": m.content[:2000],
                    "tool_calls": m.tool_calls,
                }
                for m in messages
            ],
            execution_count=exec_count,
            probe_call_count=probe_count,
        ).model_dump(),
        message="ok",
    )


@router.delete("/{session_id}", response_model=APIResponse, description="归档会话")
async def archive_session_route(session_id: str) -> APIResponse:
    deleted = await delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")

    return APIResponse(
        data={"session_id": session_id, "archived": True},
        message=f"会话 {session_id} 已删除",
    )
