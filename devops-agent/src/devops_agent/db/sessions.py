"""会话 Repository — CRUD + 分页查询

封装 sessions 表的所有数据访问操作。
所有方法均为 async，通过 aiosqlite 执行。
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

import aiosqlite

from .connection import get_db, fetchall_as_dicts
from .models import Session

logger = logging.getLogger(__name__)


async def create_session(
    title: str = "新对话",
    user_id: str = "default",
    session_id: str | None = None,
) -> Session:
    """创建新会话，返回 Session 对象。"""
    if session_id is None:
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
    db = await get_db()
    await db.execute(
        "INSERT INTO sessions (id, title, user_id) VALUES (?, ?, ?)",
        (session_id, title, user_id),
    )
    await db.commit()
    # 读回完整行（含 created_at / updated_at）
    row = await fetchall_as_dicts(
        db, "SELECT * FROM sessions WHERE id = ?", (session_id,),
    )
    return Session.from_row(row[0])


async def get_session(session_id: str) -> Optional[Session]:
    """根据 ID 获取单个会话，不存在返回 None。"""
    db = await get_db()
    row = await fetchall_as_dicts(
        db, "SELECT * FROM sessions WHERE id = ?", (session_id,),
    )
    if not row:
        return None
    return Session.from_row(row[0])


async def update_session_title(session_id: str, title: str) -> bool:
    """更新会话标题。返回是否成功（会话存在才更新）。"""
    db = await get_db()
    cursor = await db.execute(
        "UPDATE sessions SET title = ?, updated_at = datetime('now') WHERE id = ?",
        (title, session_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def list_sessions(
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Session], int]:
    """
    分页查询会话列表。

    Returns:
        (sessions, total): 会话列表和总数
    """
    db = await get_db()
    offset = (page - 1) * page_size

    # 查询条件
    where = ""
    params: tuple = ()
    if user_id:
        where = "WHERE user_id = ?"
        params = (user_id,)

    # 总数
    count_row = await fetchall_as_dicts(
        db, f"SELECT COUNT(*) as cnt FROM sessions {where}", params,
    )
    total = count_row[0]["cnt"]

    # 分页数据（按 updated_at 降序）
    rows = await fetchall_as_dicts(
        db, f"SELECT * FROM sessions {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (*params, page_size, offset),
    )
    sessions = [Session.from_row(r) for r in rows]
    return sessions, total


async def delete_session(session_id: str) -> bool:
    """删除会话（级联删除关联消息）。返回是否成功。"""
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM sessions WHERE id = ?", (session_id,),
    )
    await db.commit()
    return cursor.rowcount > 0


async def touch_session(session_id: str) -> None:
    """更新会话的 updated_at 时间戳（消息写入后调用）。"""
    db = await get_db()
    await db.execute(
        "UPDATE sessions SET updated_at = datetime('now') WHERE id = ?",
        (session_id,),
    )
    await db.commit()


__all__ = [
    "create_session",
    "get_session",
    "update_session_title",
    "list_sessions",
    "delete_session",
    "touch_session",
]
