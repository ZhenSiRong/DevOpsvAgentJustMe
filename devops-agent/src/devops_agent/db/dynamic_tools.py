"""动态工具 Repository — dynamic_tools 表的 CRUD

封装用户自定义 MCP 工具的持久化操作。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from .connection import get_db, fetchall_as_dicts
from .models import DynamicTool

logger = logging.getLogger(__name__)


async def create_dynamic_tool(
    name: str,
    description: str,
    tool_type: str,
    config: dict,
    schema_json: dict,
    created_by: str = "system",
) -> DynamicTool:
    """注册新的动态工具。"""
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO dynamic_tools
           (name, description, tool_type, config, schema_json, created_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        (
            name,
            description,
            tool_type,
            json.dumps(config, ensure_ascii=False),
            json.dumps(schema_json, ensure_ascii=False),
            created_by,
        ),
    )
    await db.commit()
    tool_id = cursor.lastrowid
    logger.info("动态工具已注册: %s (id=%s)", name, tool_id)
    return await get_dynamic_tool_by_id(tool_id)


async def get_dynamic_tool_by_id(tool_id: int) -> Optional[DynamicTool]:
    """按 ID 获取动态工具。"""
    db = await get_db()
    rows = await fetchall_as_dicts(
        db, "SELECT * FROM dynamic_tools WHERE id = ?", (tool_id,),
    )
    if not rows:
        return None
    return DynamicTool.from_row(rows[0])


async def get_dynamic_tool_by_name(name: str) -> Optional[DynamicTool]:
    """按名称获取动态工具。"""
    db = await get_db()
    rows = await fetchall_as_dicts(
        db, "SELECT * FROM dynamic_tools WHERE name = ?", (name,),
    )
    if not rows:
        return None
    return DynamicTool.from_row(rows[0])


async def list_dynamic_tools(active_only: bool = False) -> list[DynamicTool]:
    """列出所有动态工具。"""
    db = await get_db()
    if active_only:
        sql = "SELECT * FROM dynamic_tools WHERE is_active = 1 ORDER BY created_at DESC"
        rows = await fetchall_as_dicts(db, sql)
    else:
        sql = "SELECT * FROM dynamic_tools ORDER BY created_at DESC"
        rows = await fetchall_as_dicts(db, sql)
    return [DynamicTool.from_row(r) for r in rows]


async def update_dynamic_tool(
    tool_id: int,
    description: Optional[str] = None,
    config: Optional[dict] = None,
    schema_json: Optional[dict] = None,
    is_active: Optional[bool] = None,
) -> Optional[DynamicTool]:
    """更新动态工具配置。"""
    db = await get_db()
    fields = []
    values = []

    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if config is not None:
        fields.append("config = ?")
        values.append(json.dumps(config, ensure_ascii=False))
    if schema_json is not None:
        fields.append("schema_json = ?")
        values.append(json.dumps(schema_json, ensure_ascii=False))
    if is_active is not None:
        fields.append("is_active = ?")
        values.append(1 if is_active else 0)

    if not fields:
        return await get_dynamic_tool_by_id(tool_id)

    fields.append("updated_at = datetime('now')")
    sql = f"UPDATE dynamic_tools SET {', '.join(fields)} WHERE id = ?"
    values.append(tool_id)

    await db.execute(sql, tuple(values))
    await db.commit()
    logger.info("动态工具已更新: id=%s", tool_id)
    return await get_dynamic_tool_by_id(tool_id)


async def delete_dynamic_tool(tool_id: int) -> bool:
    """删除动态工具。"""
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM dynamic_tools WHERE id = ?", (tool_id,),
    )
    await db.commit()
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info("动态工具已删除: id=%s", tool_id)
    return deleted


async def toggle_dynamic_tool(tool_id: int) -> Optional[DynamicTool]:
    """切换动态工具的启用/禁用状态。"""
    db = await get_db()
    await db.execute(
        """UPDATE dynamic_tools
           SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END,
               updated_at = datetime('now')
           WHERE id = ?""",
        (tool_id,),
    )
    await db.commit()
    return await get_dynamic_tool_by_id(tool_id)


__all__ = [
    "create_dynamic_tool",
    "get_dynamic_tool_by_id",
    "get_dynamic_tool_by_name",
    "list_dynamic_tools",
    "update_dynamic_tool",
    "delete_dynamic_tool",
    "toggle_dynamic_tool",
]
