"""MCP Client —— 连接外部 MCP Server，发现工具，转发调用。

负责单个 MCP Server 的全生命周期管理：
1. 建立传输连接（stdio / sse）
2. initialize 握手
3. tools/list 工具发现
4. tools/call 工具调用
5. 心跳检测（ping）
"""

from __future__ import annotations

import logging
from typing import Any

from .protocol import (
    JSONRPCRequest,
    build_initialize_request,
    build_tools_list_request,
    build_tools_call_request,
    build_ping_request,
)
from .transport import StdioTransport

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP 客户端 —— 管理单个 MCP Server 的连接和工具调用。

    使用示例::

        client = MCPClient({
            "id": "github",
            "name": "GitHub MCP Server",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "..."},
        })
        await client.connect()
        tools = client.list_tools()
        result = await client.call_tool("search_repositories", {"query": "python"})
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.server_id = config["id"]
        self.name = config.get("name", self.server_id)

        self.transport: StdioTransport | None = None
        self._tools: list[dict] = []
        self._connected = False
        self._server_info: dict = {}

    @property
    def tools(self) -> list[dict]:
        """返回从 Server 发现的工具列表（只读副本）。"""
        return [t.copy() for t in self._tools]

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def server_info(self) -> dict:
        """返回 Server 元信息（握手响应中的 serverInfo）。"""
        return self._server_info.copy()

    def list_tools(self) -> list[dict]:
        """返回工具列表（与 tools 属性相同，便于代码可读性）。"""
        return self.tools

    async def connect(self) -> None:
        """建立连接并执行 MCP 握手 + 工具发现。"""
        if self._connected:
            logger.warning("MCP Client '%s' 已连接，跳过重复连接", self.name)
            return

        transport_type = self.config.get("transport", "stdio")

        if transport_type == "stdio":
            self.transport = StdioTransport(
                command=self.config["command"],
                args=self.config.get("args", []),
                env=self.config.get("env"),
                cwd=self.config.get("cwd"),
            )
        elif transport_type == "sse":
            raise NotImplementedError("SSE transport 尚未实现")
        else:
            raise ValueError(f"不支持的传输类型: {transport_type}")

        await self.transport.connect()

        # Step 1: initialize 握手
        init_req = build_initialize_request(req_id=1)
        init_resp = await self.transport.send(init_req)

        if init_resp.is_error:
            err = init_resp.error or {}
            await self.transport.disconnect()
            raise ConnectionError(
                f"MCP 握手失败: {err.get('code')} - {err.get('message')}"
            )

        self._server_info = (init_resp.result or {}).get("serverInfo", {})
        logger.info(
            "MCP Server 握手成功: %s v%s",
            self._server_info.get("name"),
            self._server_info.get("version"),
        )

        # Step 2: 发送 initialized 通知（无响应）
        await self._send_notification("notifications/initialized", {})

        # Step 3: 获取工具列表
        tools_req = build_tools_list_request(req_id=2)
        tools_resp = await self.transport.send(tools_req)

        if tools_resp.is_error:
            err = tools_resp.error or {}
            await self.transport.disconnect()
            raise RuntimeError(
                f"获取工具列表失败: {err.get('code')} - {err.get('message')}"
            )

        self._tools = (tools_resp.result or {}).get("tools", [])
        logger.info(
            "MCP Server '%s' 提供 %d 个工具: %s",
            self.name,
            len(self._tools),
            [t["name"] for t in self._tools],
        )

        self._connected = True

    async def disconnect(self) -> None:
        """断开连接并清理资源。"""
        if self.transport:
            await self.transport.disconnect()
            self.transport = None
        self._connected = False
        self._tools = []
        self._server_info = {}

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """调用外部 MCP Server 的工具。

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            MCP tools/call 响应的 result 字段
            （包含 content 列表，isError 标志）
        """
        if not self._connected or self.transport is None:
            return {"error": "MCP Client 未连接", "is_error": True}

        req = build_tools_call_request(
            req_id=3, name=name, arguments=arguments
        )
        resp = await self.transport.send(req)

        if resp.is_error:
            err = resp.error or {}
            return {
                "error": f"MCP 工具调用失败: {err.get('message')}",
                "is_error": True,
                "mcp_error_code": err.get("code"),
            }

        return resp.result or {}

    async def ping(self) -> bool:
        """发送心跳，检查连接状态。

        Returns:
            True: 连接正常
            False: 连接异常或已断开
        """
        if not self._connected or self.transport is None:
            return False

        try:
            req = build_ping_request(req_id=999)
            resp = await self.transport.send(req)
            return not resp.is_error
        except Exception as e:
            logger.warning("MCP ping 失败: %s", e)
            return False

    async def _send_notification(self, method: str, params: dict) -> None:
        """发送通知（无需响应）。"""
        if self.transport is None or self.transport.process is None:
            return

        req = JSONRPCRequest(method=method, params=params)
        line = req.to_json() + "\n"
        self.transport.process.stdin.write(line.encode("utf-8"))
        await self.transport.process.stdin.drain()

    def __repr__(self) -> str:
        return (
            f"<MCPClient '{self.name}' "
            f"connected={self._connected} tools={len(self._tools)}>"
        )
