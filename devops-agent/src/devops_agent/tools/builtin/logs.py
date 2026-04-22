"""内置探针：系统日志查询与文件尾读取"""

from __future__ import annotations

from typing import Any

from ...probe import journal_logs, tail_file
from ..base import ProbeTool
from ..registry import register_tool


class QueryLogsTool(ProbeTool):
    name = "query_logs"
    description = "查询系统日志(journalctl)。支持时间范围和关键词过滤。"
    parameters = {
        "type": "object",
        "properties": {
            "since": {
                "type": "string",
                "default": "1 hour ago",
                "description": "起始时间，如 '30 min ago', '2024-01-01'",
            },
            "grep": {
                "type": "string",
                "default": "",
                "description": "关键词过滤",
            },
            "lines": {
                "type": "integer",
                "default": 100,
                "minimum": 1,
                "maximum": 10000,
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        since = arguments.get("since", "1 hour ago")
        lines = arguments.get("lines", 100)
        return await journal_logs(lines=lines, since=since, timeout=30.0)


class TailFileTool(ProbeTool):
    name = "tail_file"
    description = "读取文件末尾内容。适用于查看任意日志文件的最新输出。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "文件绝对路径",
            },
            "lines": {
                "type": "integer",
                "default": 50,
            },
        },
        "required": ["path"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        path = arguments["path"]
        lines = arguments.get("lines", 50)
        return await tail_file(path=path, lines=lines, timeout=10.0)


register_tool(QueryLogsTool())
register_tool(TailFileTool())
