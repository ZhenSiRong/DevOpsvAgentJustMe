"""内置探针：系统监控（CPU、内存、负载、vmstat）"""

from __future__ import annotations

from typing import Any

from ...probe import system_top, memory_usage, system_uptime, system_vmstat
from ..base import ProbeTool
from ..registry import register_tool


class SystemTopTool(ProbeTool):
    name = "system_top"
    description = "获取 CPU/内存占用最高的 N 个进程。返回进程列表，含 PID、用户、CPU%、内存%、命令行。"
    parameters = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
                "description": "返回进程数",
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        limit = arguments.get("limit", 10)
        return await system_top(limit=limit, timeout=10.0)


class MemoryUsageTool(ProbeTool):
    name = "memory_usage"
    description = "获取系统内存用量。返回 total/used/free/shared/buff_cache/available（字节）。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await memory_usage(timeout=5.0)


class SystemUptimeTool(ProbeTool):
    name = "system_uptime"
    description = "获取系统负载与运行时长。返回 1m/5m/15m 负载、运行秒数、人类可读时长。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await system_uptime(timeout=5.0)


class SystemVmstatTool(ProbeTool):
    name = "system_vmstat"
    description = "获取系统整体状态采样（vmstat）。返回进程/内存/交换/IO/系统/CPU 指标。"
    parameters = {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "default": 3,
                "minimum": 1,
                "maximum": 10,
                "description": "采样次数",
            },
            "interval": {
                "type": "integer",
                "default": 1,
                "minimum": 1,
                "maximum": 5,
                "description": "采样间隔秒数",
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        count = arguments.get("count", 3)
        interval = arguments.get("interval", 1)
        return await system_vmstat(count=count, interval=interval, timeout=15.0)


register_tool(SystemTopTool())
register_tool(MemoryUsageTool())
register_tool(SystemUptimeTool())
register_tool(SystemVmstatTool())
