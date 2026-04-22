"""MCP 运维工具集

导入此包时自动注册所有内置工具到 ToolRegistry。
"""

from .base import MCPTool, ProbeTool, ExecutorTool
from .registry import (
    ToolRegistry,
    get_registry,
    register_tool,
    get_tool,
    list_tools,
    get_tool_definitions,
    dispatch_tool,
)

# 触发内置工具自动注册
from .builtin import *

__all__ = [
    "MCPTool", "ProbeTool", "ExecutorTool",
    "ToolRegistry", "get_registry", "register_tool",
    "get_tool", "list_tools", "get_tool_definitions", "dispatch_tool",
]
