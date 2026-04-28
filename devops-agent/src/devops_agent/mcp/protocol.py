"""MCP 协议层 —— JSON-RPC 2.0 消息格式 + MCP 标准消息类型

不依赖外部 mcp SDK，手写轻量级实现。
兼容协议版本: 2024-11-05
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

# MCP 协议版本
MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 请求消息。"""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "JSONRPCRequest":
        return cls(
            jsonrpc=d.get("jsonrpc", "2.0"),
            id=d.get("id"),
            method=d.get("method", ""),
            params=d.get("params", {}),
        )


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 响应消息。"""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any = None
    error: dict | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, d: dict) -> "JSONRPCResponse":
        return cls(
            jsonrpc=d.get("jsonrpc", "2.0"),
            id=d.get("id"),
            result=d.get("result"),
            error=d.get("error"),
        )

    @property
    def is_error(self) -> bool:
        return self.error is not None


# ============================================================
#  MCP 标准消息构造器
# ============================================================


def build_initialize_request(req_id: int = 1) -> JSONRPCRequest:
    """构建 MCP initialize 请求。"""
    return JSONRPCRequest(
        id=req_id,
        method="initialize",
        params={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": True},
                "logging": {},
            },
            "clientInfo": {
                "name": "devops-agent",
                "version": "1.0.0",
            },
        },
    )


def build_tools_list_request(req_id: int = 2) -> JSONRPCRequest:
    """构建 MCP tools/list 请求。"""
    return JSONRPCRequest(
        id=req_id,
        method="tools/list",
        params={},
    )


def build_tools_call_request(
    req_id: int, name: str, arguments: dict
) -> JSONRPCRequest:
    """构建 MCP tools/call 请求。"""
    return JSONRPCRequest(
        id=req_id,
        method="tools/call",
        params={
            "name": name,
            "arguments": arguments,
        },
    )


def build_ping_request(req_id: int) -> JSONRPCRequest:
    """构建 MCP ping 请求（心跳）。"""
    return JSONRPCRequest(
        id=req_id,
        method="ping",
        params={},
    )
