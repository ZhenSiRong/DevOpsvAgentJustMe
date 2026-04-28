"""内置探针：进程管理扩展（进程查找、进程树、打开文件）"""

from __future__ import annotations

from typing import Any

from ...probe import process_find, process_tree, list_open_files
from ..base import ProbeTool
from ..registry import register_tool


class ProcessFindTool(ProbeTool):
    name = "process_find"
    description = "按名称模式查找进程 PID。返回匹配的 PID 和命令行。"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "进程名匹配模式",
            },
        },
        "required": ["pattern"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await process_find(pattern=arguments["pattern"], timeout=10.0)


class ProcessTreeTool(ProbeTool):
    name = "process_tree"
    description = "获取进程树。返回 pstree 文本输出和扁平化的父子进程关系列表。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await process_tree(timeout=10.0)


class ListOpenFilesTool(ProbeTool):
    name = "list_open_files"
    description = "列出进程打开的文件、端口或连接。使用 lsof，支持按 PID、端口、路径过滤。"
    parameters = {
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "description": "按进程 PID 过滤",
            },
            "port": {
                "type": "integer",
                "description": "按端口号过滤",
            },
            "path": {
                "type": "string",
                "description": "按文件路径过滤",
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await list_open_files(
            pid=arguments.get("pid"),
            port=arguments.get("port"),
            path=arguments.get("path"),
            timeout=15.0,
        )


register_tool(ProcessFindTool())
register_tool(ProcessTreeTool())
register_tool(ListOpenFilesTool())
