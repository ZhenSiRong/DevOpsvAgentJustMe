"""幂等控制 + 操作状态机

提供：
1. 幂等键（Idempotency Key）：防止重复执行同一操作
2. 操作状态机：pending → in_progress → success/failed/timedout/blocked/rolled_back

使用方式：
    from .idempotency import IdempotencyGuard, OperationState

    guard = IdempotencyGuard()
    
    # 检查幂等
    existing = await guard.check("key-123")
    if existing and existing.state == OperationState.SUCCESS:
        return existing.result
    
    # 标记进行中
    await guard.mark_in_progress("key-123")
    ...
    # 标记完成
    await guard.mark_complete("key-123", OperationState.SUCCESS, result)
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OperationState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEDOUT = "timedout"
    BLOCKED = "blocked"
    ROLLED_BACK = "rolled_back"


@dataclass
class OperationRecord:
    key: str
    state: OperationState = OperationState.PENDING
    result: Any = None
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)


class IdempotencyGuard:
    """幂等守卫 — 内存缓存 + 自动过期

    生产环境建议迁移到 SQLite/Redis。
    """

    MAX_RECORDS = 1000       # 最大记录数
    TTL_SECONDS = 3600       # 记录过期时间（1小时）

    def __init__(self) -> None:
        self._records: dict[str, OperationRecord] = {}

    async def check(self, key: str) -> OperationRecord | None:
        """检查幂等键是否已存在"""
        rec = self._records.get(key)
        if rec is None:
            return None

        # TTL 检查
        if time.monotonic() - rec.created_at > self.TTL_SECONDS:
            del self._records[key]
            return None

        return rec

    async def mark_in_progress(self, key: str) -> None:
        """标记操作为进行中"""
        self._gc_if_needed()
        self._records[key] = OperationRecord(
            key=key,
            state=OperationState.IN_PROGRESS,
        )

    async def mark_complete(
        self,
        key: str,
        state: OperationState,
        result: Any = None,
    ) -> None:
        """标记操作完成"""
        rec = self._records.get(key)
        if rec:
            rec.state = state
            rec.result = result
            rec.updated_at = time.monotonic()
        else:
            self._records[key] = OperationRecord(
                key=key,
                state=state,
                result=result,
            )

    def _gc_if_needed(self) -> None:
        """记录数超过上限时清理过期项"""
        if len(self._records) < self.MAX_RECORDS:
            return
        now = time.monotonic()
        expired = [
            k for k, v in self._records.items()
            if now - v.created_at > self.TTL_SECONDS
        ]
        for k in expired:
            del self._records[k]
        logger.debug("幂等守卫 GC: %d 条", len(expired))


# 全局单例
_idempotency_guard: IdempotencyGuard | None = None


def get_idempotency_guard() -> IdempotencyGuard:
    global _idempotency_guard
    if _idempotency_guard is None:
        _idempotency_guard = IdempotencyGuard()
    return _idempotency_guard


__all__ = [
    "IdempotencyGuard",
    "OperationState",
    "OperationRecord",
    "get_idempotency_guard",
]
