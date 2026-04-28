"""内置探针：网络诊断扩展（ping、路由追踪、HTTP探测、socket详情）"""

from __future__ import annotations

from typing import Any

from ...probe import ping_host, trace_route, http_probe, socket_list
from ..base import ProbeTool
from ..registry import register_tool


class PingHostTool(ProbeTool):
    name = "ping_host"
    description = "对目标主机执行 ping 连通性测试。返回丢包率、RTT min/avg/max/mdev。"
    parameters = {
        "type": "object",
        "properties": {
            "host": {
                "type": "string",
                "description": "目标主机名或 IP",
            },
            "count": {
                "type": "integer",
                "default": 4,
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["host"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await ping_host(
            host=arguments["host"],
            count=arguments.get("count", 4),
            timeout=15.0,
        )


class TraceRouteTool(ProbeTool):
    name = "trace_route"
    description = "路由追踪。返回每跳的 IP 地址和延迟。"
    parameters = {
        "type": "object",
        "properties": {
            "host": {
                "type": "string",
                "description": "目标主机名或 IP",
            },
        },
        "required": ["host"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await trace_route(host=arguments["host"], timeout=30.0)


class HttpProbeTool(ProbeTool):
    name = "http_probe"
    description = "HTTP 探测。返回状态码、响应时间、Content-Type。"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "目标 URL，如 http://localhost:8080",
            },
        },
        "required": ["url"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await http_probe(url=arguments["url"], timeout=10.0)


class SocketListTool(ProbeTool):
    name = "socket_list"
    description = "获取 Socket 统计（ss 命令增强版）。返回 TCP/UDP 连接的详细状态、接收/发送队列、进程信息。"
    parameters = {
        "type": "object",
        "properties": {
            "protocol": {
                "type": "string",
                "enum": ["tcp", "udp", "unix"],
                "description": "协议过滤",
            },
            "state": {
                "type": "string",
                "description": "状态过滤，如 ESTAB、LISTEN、TIME-WAIT",
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await socket_list(
            protocol=arguments.get("protocol"),
            state=arguments.get("state"),
            timeout=10.0,
        )


register_tool(PingHostTool())
register_tool(TraceRouteTool())
register_tool(HttpProbeTool())
register_tool(SocketListTool())
