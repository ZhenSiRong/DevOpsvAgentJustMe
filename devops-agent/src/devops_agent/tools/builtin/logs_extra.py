"""内置探针：日志分析扩展（dmesg、日志切片）"""

from __future__ import annotations

from typing import Any

from ...probe import kernel_messages, log_slice
from ..base import ProbeTool
from ..registry import register_tool


class KernelMessagesTool(ProbeTool):
    name = "kernel_messages"
    description = "获取内核环形缓冲日志（dmesg）。支持按日志级别过滤。"
    parameters = {
        "type": "object",
        "properties": {
            "level": {
                "type": "string",
                "description": "日志级别过滤，如 err,warn",
            },
            "lines": {
                "type": "integer",
                "default": 100,
                "minimum": 1,
                "maximum": 1000,
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await kernel_messages(
            level=arguments.get("level"),
            lines=arguments.get("lines", 100),
            timeout=10.0,
        )


class LogSliceTool(ProbeTool):
    name = "log_slice"
    description = "按行号范围提取日志文件内容。支持起始行和结束行。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "日志文件路径",
            },
            "start_line": {
                "type": "integer",
                "default": 1,
                "minimum": 1,
                "description": "起始行号（1-based）",
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（None 则到文件末尾）",
            },
        },
        "required": ["path"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await log_slice(
            path=arguments["path"],
            start_line=arguments.get("start_line", 1),
            end_line=arguments.get("end_line"),
            timeout=10.0,
        )


register_tool(KernelMessagesTool())
register_tool(LogSliceTool())
