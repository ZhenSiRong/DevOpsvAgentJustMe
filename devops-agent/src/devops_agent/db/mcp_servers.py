"""MCP Server 配置 Repository — mcp_servers 表的 CRUD

管理外部 MCP Server 的连接配置持久化。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from .connection import get_db, fetchall_as_dicts
from .models import MCPServer

logger = logging.getLogger(__name__)


async def create_mcp_server(
    server_id: str,
    name: str,
    transport: str,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    url: str | None = None,
    cwd: str | None = None,
) -> MCPServer:
    """注册新的 MCP Server 配置。"""
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO mcp_servers
           (id, name, transport, command, args, env, url, cwd, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))""",
        (
            server_id,
            name,
            transport,
            command,
            json.dumps(args or [], ensure_ascii=False),
            json.dumps(env or {}, ensure_ascii=False),
            url,
            cwd,
        ),
    )
    await db.commit()
    logger.info("MCP Server 配置已注册: %s (%s)", name, server_id)
    return await get_mcp_server_by_id(server_id)


async def get_mcp_server_by_id(server_id: str) -> Optional[MCPServer]:
    """按 ID 获取 MCP Server 配置。"""
    db = await get_db()
    rows = await fetchall_as_dicts(
        db, "SELECT * FROM mcp_servers WHERE id = ?", (server_id,),
    )
    if not rows:
        return None
    return MCPServer.from_row(rows[0])


async def list_mcp_servers(active_only: bool = False) -> list[MCPServer]:
    """列出所有 MCP Server 配置。"""
    db = await get_db()
    if active_only:
        sql = "SELECT * FROM mcp_servers WHERE is_active = 1 ORDER BY created_at DESC"
        rows = await fetchall_as_dicts(db, sql)
    else:
        sql = "SELECT * FROM mcp_servers ORDER BY created_at DESC"
        rows = await fetchall_as_dicts(db, sql)
    return [MCPServer.from_row(r) for r in rows]


async def update_mcp_server(
    server_id: str,
    name: Optional[str] = None,
    command: Optional[str] = None,
    args: Optional[list[str]] = None,
    env: Optional[dict[str, str]] = None,
    url: Optional[str] = None,
    cwd: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Optional[MCPServer]:
    """更新 MCP Server 配置。"""
    db = await get_db()
    fields = []
    values = []

    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if command is not None:
        fields.append("command = ?")
        values.append(command)
    if args is not None:
        fields.append("args = ?")
        values.append(json.dumps(args, ensure_ascii=False))
    if env is not None:
        fields.append("env = ?")
        values.append(json.dumps(env, ensure_ascii=False))
    if url is not None:
        fields.append("url = ?")
        values.append(url)
    if cwd is not None:
        fields.append("cwd = ?")
        values.append(cwd)
    if is_active is not None:
        fields.append("is_active = ?")
        values.append(1 if is_active else 0)

    if not fields:
        return await get_mcp_server_by_id(server_id)

    fields.append("updated_at = datetime('now')")
    sql = f"UPDATE mcp_servers SET {', '.join(fields)} WHERE id = ?"
    values.append(server_id)

    await db.execute(sql, tuple(values))
    await db.commit()
    logger.info("MCP Server 配置已更新: %s", server_id)
    return await get_mcp_server_by_id(server_id)


async def delete_mcp_server(server_id: str) -> bool:
    """删除 MCP Server 配置。"""
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM mcp_servers WHERE id = ?", (server_id,),
    )
    await db.commit()
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info("MCP Server 配置已删除: %s", server_id)
    return deleted


async def toggle_mcp_server(server_id: str) -> Optional[MCPServer]:
    """切换 MCP Server 的启用/禁用状态。"""
    db = await get_db()
    await db.execute(
        """UPDATE mcp_servers
           SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END,
               updated_at = datetime('now')
           WHERE id = ?""",
        (server_id,),
    )
    await db.commit()
    return await get_mcp_server_by_id(server_id)


__all__ = [
    "create_mcp_server",
    "get_mcp_server_by_id",
    "list_mcp_servers",
    "update_mcp_server",
    "delete_mcp_server",
    "toggle_mcp_server",
]
