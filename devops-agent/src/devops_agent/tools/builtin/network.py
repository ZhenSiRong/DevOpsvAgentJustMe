"""内置探针：网络连接、接口与 DNS 解析"""

from __future__ import annotations

from typing import Any

from ...probe import network_connections, network_interfaces, dns_resolve
from ..base import ProbeTool
from ..registry import register_tool


class NetworkConnectionsTool(ProbeTool):
    name = "network_connections"
    description = "查看当前网络连接（TCP/UDP）、监听端口。用于排查网络问题。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await network_connections()


class NetworkInterfacesTool(ProbeTool):
    name = "network_interfaces"
    description = "查看网络接口配置信息（IP 地址、MAC、状态）。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await network_interfaces()


class DNSResolveTool(ProbeTool):
    name = "dns_resolve"
    description = "DNS 解析测试，查询域名的 IP 地址。用于诊断 DNS 问题。"
    parameters = {
        "type": "object",
        "properties": {
            "hostname": {
                "type": "string",
                "description": "要解析的域名",
            },
        },
        "required": ["hostname"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        hostname = arguments["hostname"]
        return await dns_resolve(hostname=hostname)


register_tool(NetworkConnectionsTool())
register_tool(NetworkInterfacesTool())
register_tool(DNSResolveTool())
