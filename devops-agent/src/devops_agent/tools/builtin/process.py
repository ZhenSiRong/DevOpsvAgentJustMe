"""内置探针：进程列表与进程详情"""

from __future__ import annotations

from typing import Any

from ...probe import process_list, process_detail
from ..base import ProbeTool
from ..registry import register_tool


class ProcessListTool(ProbeTool):
    name = "process_list"
    description = "列出系统进程。可按进程名过滤。返回 PID、CPU%、MEM%、命令等。"
    parameters = {
        "type": "object",
        "properties": {
            "filter_str": {
                "type": "string",
                "default": "",
                "description": "按进程名模糊匹配过滤，为空则返回所有进程",
            },
            "limit": {
                "type": "integer",
                "default": 50,
                "minimum": 1,
                "maximum": 500,
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        f = arguments.get("filter_str", "")
        return await process_list(filter_str=f, timeout=15.0)


class ProcessDetailTool(ProbeTool):
    name = "process_detail"
    description = "获取单个进程的详细信息（PID、状态、打开的文件数、线程数等）。"
    parameters = {
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "description": "目标进程的 PID",
            },
        },
        "required": ["pid"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        pid = arguments["pid"]
        return await process_detail(pid=pid)


register_tool(ProcessListTool())
register_tool(ProcessDetailTool())
