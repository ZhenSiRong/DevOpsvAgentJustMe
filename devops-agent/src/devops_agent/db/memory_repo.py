"""记忆数据访问层 —— 跨会话长期记忆的 CRUD"""

from __future__ import annotations

import logging
from typing import Optional

from .connection import get_db
from .models import Memory

logger = logging.getLogger(__name__)


async def add_memory(
    type: str,
    content: str,
    source_session_id: Optional[str] = None,
    importance: float = 1.0,
) -> int:
    """添加一条记忆，返回记忆 ID"""
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO memories (type, content, source_session_id, importance)
        VALUES (?, ?, ?, ?)
        """,
        (type, content, source_session_id, importance),
    )
    await db.commit()
    logger.debug("记忆已添加: type=%s, id=%s", type, cursor.lastrowid)
    return cursor.lastrowid or 0


async def get_memory(memory_id: int) -> Optional[Memory]:
    """按 ID 获取记忆"""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM memories WHERE id = ?", (memory_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return Memory.from_row(row)
    return None


async def query_memories(
    type: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 10,
    min_importance: float = 0.0,
) -> list[Memory]:
    """
    检索记忆。

    支持按类型过滤、关键词模糊匹配、最低重要性筛选。
    结果按 importance 降序排列。
    """
    db = await get_db()
    conditions = ["importance >= ?"]
    params: list = [min_importance]

    if type:
        conditions.append("type = ?")
        params.append(type)

    if keyword:
        conditions.append("content LIKE ?")
        params.append(f"%{keyword}%")

    where_clause = " AND ".join(conditions)
    sql = f"""
        SELECT * FROM memories
        WHERE {where_clause}
        ORDER BY importance DESC, updated_at DESC
        LIMIT ?
    """
    params.append(limit)

    async with db.execute(sql, params) as cursor:
        rows = await cursor.fetchall()
        return [Memory.from_row(row) for row in rows]


async def increment_access_count(memory_id: int) -> None:
    """增加记忆的访问计数和更新时间"""
    db = await get_db()
    await db.execute(
        """
        UPDATE memories
        SET access_count = access_count + 1, updated_at = datetime('now')
        WHERE id = ?
        """,
        (memory_id,),
    )
    await db.commit()


async def delete_memory(memory_id: int) -> bool:
    """删除指定记忆，返回是否成功"""
    db = await get_db()
    cursor = await db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    await db.commit()
    return cursor.rowcount > 0


async def get_memory_stats() -> dict:
    """获取记忆统计信息"""
    db = await get_db()
    async with db.execute(
        "SELECT type, COUNT(*) as cnt FROM memories GROUP BY type"
    ) as cursor:
        rows = await cursor.fetchall()
        type_counts = {row["type"]: row["cnt"] for row in rows}

    async with db.execute("SELECT COUNT(*) as total FROM memories") as cursor:
        row = await cursor.fetchone()
        total = row["total"] if row else 0

    return {
        "total": total,
        "by_type": type_counts,
    }


__all__ = [
    "add_memory",
    "get_memory",
    "query_memories",
    "increment_access_count",
    "delete_memory",
    "get_memory_stats",
]