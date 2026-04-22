"""消息 Repository — 追加 + 按会话查询

封装 messages 表的所有数据访问操作。
消息为 append-only 模式，不支持修改和删除（审计要求）。
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

import aiosqlite

from .connection import get_db, fetchall_as_dicts
from .models import Message

logger = logging.getLogger(__name__)


async def append_message(
    session_id: str,
    role: str,
    content: str,
    tool_calls: Optional[list[dict]] = None,
    audit_trail: Optional[list[str]] = None,
    token_count: Optional[int] = None,
) -> Message:
    """
    向指定会话追加一条消息。

    Returns:
        新创建的 Message 对象
    """
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    db = await get_db()
    await db.execute(
        """INSERT INTO messages
           (id, session_id, role, content, tool_calls, audit_trail, token_count)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            msg_id,
            session_id,
            role,
            content,
            json.dumps(tool_calls or [], ensure_ascii=False),
            json.dumps(audit_trail or []),
            token_count,
        ),
    )
    await db.commit()

    row = await fetchall_as_dicts(
        db, "SELECT * FROM messages WHERE id = ?", (msg_id,),
    )
    return Message.from_row(row[0])


async def get_messages_by_session(
    session_id: str,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Message], int]:
    """
    分页获取指定会话的消息列表（按时间正序）。

    Returns:
        (messages, total)
    """
    db = await get_db()
    offset = (page - 1) * page_size

    count_row = await fetchall_as_dicts(
        db, "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
        (session_id,),
    )
    total = count_row[0]["cnt"]

    rows = await fetchall_as_dicts(
        db, """SELECT * FROM messages
           WHERE session_id = ?
           ORDER BY created_at ASC
           LIMIT ? OFFSET ?""",
        (session_id, page_size, offset),
    )
    messages = [Message.from_row(r) for r in rows]
    return messages, total


async def get_session_messages_all(session_id: str) -> list[Message]:
    """
    获取指定会话的全部消息（不分页，用于构建 LLM 上下文）。
    注意：超长对话应使用 conversation_state.context_summary 做压缩。
    """
    db = await get_db()
    rows = await fetchall_as_dicts(
        db, """SELECT * FROM messages
           WHERE session_id = ?
           ORDER BY created_at ASC""",
        (session_id,),
    )
    return [Message.from_row(r) for r in rows]


async def count_messages_by_session(session_id: str) -> int:
    """统计指定会话的消息数量。"""
    db = await get_db()
    row = await fetchall_as_dicts(
        db, "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
        (session_id,),
    )
    return row[0]["cnt"]


__all__ = [
    "append_message",
    "get_messages_by_session",
    "get_session_messages_all",
    "count_messages_by_session",
]
