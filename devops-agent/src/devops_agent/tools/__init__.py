"""MCP 运维工具集

导入此包时自动注册所有内置工具到 ToolRegistry。
"""

from .base import MCPTool, ProbeTool, ExecutorTool
from .registry import (
    ToolRegistry,
    get_registry,
    register_tool,
    register_builtin_tool,
    get_tool,
    list_tools,
    get_tool_definitions,
    dispatch_tool,
)
from .dynamic import DynamicMCPTool

# 触发内置工具自动注册
from .builtin import *

# 标记所有已注册工具为内置（防止被动态工具覆盖）
_registry = get_registry()
for _tool in _registry.list_tools():
    _registry._builtin_names.add(_tool.name)

__all__ = [
    "MCPTool", "ProbeTool", "ExecutorTool", "DynamicMCPTool",
    "ToolRegistry", "get_registry", "register_tool", "register_builtin_tool",
    "get_tool", "list_tools", "get_tool_definitions", "dispatch_tool",
]
