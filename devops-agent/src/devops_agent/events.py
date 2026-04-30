"""事件总线 — 轻量级发布/订阅系统

用于模块间解耦通信：
- 审计日志写入
- Metrics 指标记录
- 通知推送（预留）
- 推理链路日志

使用方式：
    from .event_bus import EventBus, bus

    @bus.on("command_executed")
    async def handle(event):
        await audit_log(event)
    
    await bus.emit("command_executed", {"command": "ls"})
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    """异步事件总线"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._event_count: dict[str, int] = defaultdict(int)

    def on(self, event_type: str) -> Callable:
        """装饰器：注册事件处理器"""
        def decorator(handler: EventHandler) -> EventHandler:
            self._handlers[event_type].append(handler)
            return handler
        return decorator

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """手动订阅事件"""
        self._handlers[event_type].append(handler)

    async def emit(self, event_type: str, data: dict[str, Any]) -> None:
        """发布事件（fire-and-forget，不阻塞调用方）"""
        self._event_count[event_type] += 1

        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        # 并行执行所有处理器，任一失败不影响其他
        tasks = []
        for handler in handlers:
            tasks.append(self._safe_call(handler, event_type, data))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(self, handler: EventHandler, event_type: str, data: dict) -> None:
        try:
            await handler(data)
        except Exception as e:
            logger.error("事件处理器异常 [%s]: %s", event_type, e, exc_info=True)

    def stats(self) -> dict[str, Any]:
        return {
            "handlers": {k: len(v) for k, v in self._handlers.items()},
            "events": dict(self._event_count),
        }


# 全局单例
bus = EventBus()


# ============================================================
#  内置事件处理器（解耦审计 + Metrics）
# ============================================================

@bus.on("command_executed")
async def _on_command_executed(data: dict) -> None:
    """命令执行后：记录 Metrics"""
    from .metrics import record_command_executed
    record_command_executed(data.get("status", "UNKNOWN"))


@bus.on("llm_called")
async def _on_llm_called(data: dict) -> None:
    """LLM 调用后：记录 Metrics"""
    from .metrics import record_llm_call
    record_llm_call(
        protocol=data.get("protocol", "openai"),
        duration=data.get("duration", 0.0),
    )


@bus.on("tool_called")
async def _on_tool_called(data: dict) -> None:
    """工具调用后：记录 Metrics"""
    from .metrics import record_tool_call
    record_tool_call(
        tool_name=data.get("tool_name", "unknown"),
        duration=data.get("duration", 0.0),
    )


@bus.on("security_blocked")
async def _on_security_blocked(data: dict) -> None:
    """安全拦截后：记录 Metrics"""
    from .metrics import record_security_block
    record_security_block()


__all__ = ["EventBus", "bus"]
