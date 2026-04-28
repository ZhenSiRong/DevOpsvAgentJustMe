"""内置探针：文件系统操作（目录大小、IO统计、块设备、文件查询）"""

from __future__ import annotations

from typing import Any

from ...probe import (
    directory_size, disk_iostat, block_devices,
    list_directory, find_files, file_stat, file_type, read_file,
)
from ..base import ProbeTool
from ..registry import register_tool


class DirectorySizeTool(ProbeTool):
    name = "directory_size"
    description = "获取指定目录的总大小及子目录分布。使用 du 命令，返回人类可读大小。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "default": "/var/log",
                "description": "目标目录",
            },
            "depth": {
                "type": "integer",
                "default": 1,
                "minimum": 0,
                "maximum": 5,
                "description": "递归深度",
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        path = arguments.get("path", "/var/log")
        depth = arguments.get("depth", 1)
        return await directory_size(path=path, depth=depth, timeout=30.0)


class DiskIostatTool(ProbeTool):
    name = "disk_iostat"
    description = "获取磁盘 IO 统计。返回设备级读写速率、IOPS、队列深度、利用率。"
    parameters = {
        "type": "object",
        "properties": {
            "samples": {
                "type": "integer",
                "default": 3,
                "minimum": 1,
                "maximum": 10,
            },
            "interval": {
                "type": "integer",
                "default": 1,
                "minimum": 1,
                "maximum": 5,
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        samples = arguments.get("samples", 3)
        interval = arguments.get("interval", 1)
        return await disk_iostat(samples=samples, interval=interval, timeout=15.0)


class BlockDevicesTool(ProbeTool):
    name = "block_devices"
    description = "获取块设备信息。返回磁盘/分区/挂载点/LVM 结构。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await block_devices(timeout=10.0)


class ListDirectoryTool(ProbeTool):
    name = "list_directory"
    description = "列出目录内容。返回文件名、类型、权限、所有者、大小、修改时间。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "default": "/",
                "description": "目标目录",
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        path = arguments.get("path", "/")
        return await list_directory(path=path, timeout=10.0)


class FindFilesTool(ProbeTool):
    name = "find_files"
    description = "搜索文件。支持按名称模式、类型、大小、修改时间过滤。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "default": "/",
                "description": "搜索起始路径",
            },
            "name": {
                "type": "string",
                "description": "文件名模式，如 *.log",
            },
            "ftype": {
                "type": "string",
                "enum": ["f", "d", "l"],
                "description": "文件类型：f=文件, d=目录, l=链接",
            },
            "size": {
                "type": "string",
                "description": "大小条件，如 +100M, -1G",
            },
            "mtime": {
                "type": "integer",
                "description": "修改天数，如 +7 表示7天前",
            },
            "limit": {
                "type": "integer",
                "default": 100,
                "minimum": 1,
                "maximum": 500,
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await find_files(
            path=arguments.get("path", "/"),
            name=arguments.get("name"),
            ftype=arguments.get("ftype"),
            size=arguments.get("size"),
            mtime=arguments.get("mtime"),
            limit=arguments.get("limit", 100),
            timeout=30.0,
        )


class FileStatTool(ProbeTool):
    name = "file_stat"
    description = "获取文件元信息。返回大小、权限、所有者、inode、链接数、时间戳。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目标文件路径",
            },
        },
        "required": ["path"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await file_stat(path=arguments["path"], timeout=5.0)


class FileTypeTool(ProbeTool):
    name = "file_type"
    description = "检测文件类型。返回 MIME 类型和描述。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目标文件路径",
            },
        },
        "required": ["path"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await file_type(path=arguments["path"], timeout=5.0)


class ReadFileTool(ProbeTool):
    name = "read_file"
    description = "读取文件内容。支持限制行数和起始偏移。默认最多返回500行。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目标文件路径",
            },
            "lines": {
                "type": "integer",
                "default": 500,
                "minimum": 1,
                "maximum": 2000,
                "description": "读取行数",
            },
            "offset": {
                "type": "integer",
                "default": 0,
                "minimum": 0,
                "description": "起始行偏移（0-based）",
            },
        },
        "required": ["path"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await read_file(
            path=arguments["path"],
            lines=arguments.get("lines", 500),
            offset=arguments.get("offset", 0),
            timeout=10.0,
        )


register_tool(DirectorySizeTool())
register_tool(DiskIostatTool())
register_tool(BlockDevicesTool())
register_tool(ListDirectoryTool())
register_tool(FindFilesTool())
register_tool(FileStatTool())
register_tool(FileTypeTool())
register_tool(ReadFileTool())
