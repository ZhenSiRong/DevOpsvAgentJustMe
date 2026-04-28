"""MCP (Model Context Protocol) 兼容层

为 DevOps Agent 提供标准 MCP 协议支持：
- Client: 连接外部 MCP Server，将其工具接入本地 Agent
- Server: 将本地 ToolRegistry 暴露为标准 MCP Server
- Transport: stdio 传输层（SSE 后续扩展）

不依赖外部 mcp SDK，手写轻量级实现。
兼容协议版本: 2024-11-05
"""

from .protocol import (
    JSONRPCRequest,
    JSONRPCResponse,
    build_initialize_request,
    build_tools_list_request,
    build_tools_call_request,
    build_ping_request,
    MCP_PROTOCOL_VERSION,
)
from .transport import StdioTransport
from .client import MCPClient

# Note: ExternalMCPTool / MCPServerAdapter 从子模块直接导入，
# 避免 __init__ 层触发循环导入（tools.base <-> agent.core）
# from .adapter import ExternalMCPTool
# from .server import MCPServerAdapter, run_mcp_server

__all__ = [
    "JSONRPCRequest",
    "JSONRPCResponse",
    "build_initialize_request",
    "build_tools_list_request",
    "build_tools_call_request",
    "build_ping_request",
    "MCP_PROTOCOL_VERSION",
    "StdioTransport",
    "MCPClient",
]
