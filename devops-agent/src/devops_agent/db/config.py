"""配置 KV Repository — 键值对读写

封装 configs 表的数据访问。
用于存储 LLM 模型参数、系统设置等运行时配置。
"""

from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

from .connection import get_db, fetchall_as_dicts
from .models import Config

logger = logging.getLogger(__name__)


async def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    """读取单个配置值，不存在返回 default。"""
    db = await get_db()
    row = await fetchall_as_dicts(
        db, "SELECT value FROM configs WHERE key = ?", (key,),
    )
    if not row:
        return default
    return row[0]["value"]


async def set_config(key: str, value: str) -> None:
    """写入或更新配置（UPSERT 语义）。"""
    db = await get_db()
    await db.execute(
        """INSERT INTO configs (key, value, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')""",
        (key, value),
    )
    await db.commit()
    logger.debug("配置已更新: %s", key)


async def get_all_configs() -> list[Config]:
    """获取全部配置（管理界面用）。"""
    db = await get_db()
    rows = await fetchall_as_dicts(
        db, "SELECT * FROM configs ORDER BY key",
    )
    return [Config.from_row(r) for r in rows]


async def delete_config(key: str) -> bool:
    """删除指定配置。返回是否成功。"""
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM configs WHERE key = ?", (key,),
    )
    await db.commit()
    return cursor.rowcount > 0


__all__ = [
    "get_config",
    "set_config",
    "get_all_configs",
    "delete_config",
]
