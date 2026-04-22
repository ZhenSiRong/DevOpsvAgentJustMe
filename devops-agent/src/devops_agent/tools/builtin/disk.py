"""内置探针：磁盘使用与大文件扫描"""

from __future__ import annotations

from typing import Any

from ...probe import disk_usage, large_files
from ..base import ProbeTool
from ..registry import register_tool


class DiskUsageTool(ProbeTool):
    name = "disk_usage"
    description = "查看指定路径的磁盘使用情况。返回总空间、已用、可用、使用率百分比。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "default": "/",
                "description": "要查看的文件系统路径，默认根分区 /",
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await disk_usage(timeout=30.0)


class LargeFilesTool(ProbeTool):
    name = "large_files"
    description = "扫描指定目录下最大的 N 个文件。用于定位占用空间大的文件。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "default": "/",
            },
            "limit": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        path = arguments.get("path", "/var/log")
        top_n = arguments.get("limit", 10)
        return await large_files(path=path, top_n=top_n, timeout=30.0)


# 模块导入时自动注册
register_tool(DiskUsageTool())
register_tool(LargeFilesTool())
