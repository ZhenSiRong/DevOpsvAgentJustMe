"""MCP Server 适配器 —— 将本地 ToolRegistry 暴露为标准 MCP Server。

通过 stdio 模式对外提供服务，使 Claude Desktop、Cline、Cursor 等
MCP Client 可以调用我们的 DevOps 工具。

入口::

    python -m devops_agent.mcp.server

或使用 run_mcp_server() 直接启动。
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from ..tools.registry import get_registry

logger = logging.getLogger(__name__)


class MCPServerAdapter:
    """本地工具 MCP Server 适配器。

    从 stdin 读取 JSON-RPC 请求，通过 stdout 返回响应。
    将本地 ToolRegistry 中注册的所有工具暴露为标准 MCP 工具。
    """

    def __init__(self):
        self.registry = get_registry()
        self._initialized = False

    async def run(self) -> None:
        """主循环 —— 从 stdin 读取请求并处理。"""
        logger.info("DevOps Agent MCP Server 已启动")

        # 设置行缓冲模式
        sys.stdin = open(sys.stdin.fileno(), mode="r", encoding="utf-8")
        sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8")

        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                await self._handle_message(line)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("MCP Server 处理异常: %s", e)

        logger.info("DevOps Agent MCP Server 已停止")

    async def _handle_message(self, line: str) -> None:
        """处理单条 JSON-RPC 消息。"""
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            self._send_error(None, -32700, "Parse error")
            return

        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        # 通知类消息（无 id）
        if msg_id is None:
            if method == "notifications/initialized":
                logger.debug("收到 initialized 通知")
            else:
                logger.debug("收到未处理通知: %s", method)
            return

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "tools/list":
                result = self._handle_tools_list(params)
            elif method == "tools/call":
                result = await self._handle_tools_call(params)
            elif method == "ping":
                result = {}
            else:
                self._send_error(msg_id, -32601, f"Method not found: {method}")
                return

            self._send_response(msg_id, result)

        except Exception as e:
            logger.error("处理 %s 时异常: %s", method, e)
            self._send_error(msg_id, -32603, f"Internal error: {e}")

    def _handle_initialize(self, params: dict) -> dict:
        """处理 initialize 请求。"""
        client_version = params.get("protocolVersion", "")
        client_info = params.get("clientInfo", {})
        logger.info(
            "MCP Client 握手: %s v%s protocol=%s",
            client_info.get("name"),
            client_info.get("version"),
            client_version,
        )

        self._initialized = True
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": "devops-agent",
                "version": "1.0.0",
            },
        }

    def _handle_tools_list(self, params: dict) -> dict:
        """返回本地注册的所有工具列表。"""
        tools = []
        for tool in self.registry.list_tools():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.parameters,
            })
        return {"tools": tools}

    async def _handle_tools_call(self, params: dict) -> dict:
        """执行工具调用并将结果转换为 MCP 格式。"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        logger.info("MCP Server 收到工具调用: %s(%s)", name, arguments)

        # 构造一个最小 AgentContext（外部调用没有会话上下文）
        ctx = {"session_id": "mcp-external", "tool_round": 0}

        try:
            result = await self.registry.execute(name, arguments, ctx)

            # 转换为 MCP content 格式
            text = json.dumps(result, ensure_ascii=False, default=str)
            return {
                "content": [{"type": "text", "text": text}],
                "isError": result.get("is_error", False),
            }
        except Exception as e:
            logger.error("MCP 工具执行异常: %s", e)
            return {
                "content": [{"type": "text", "text": f"执行异常: {e}"}],
                "isError": True,
            }

    def _send_response(self, msg_id: Any, result: Any) -> None:
        """发送 JSON-RPC 成功响应。"""
        resp = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }
        self._write(resp)

    def _send_error(self, msg_id: Any, code: int, message: str) -> None:
        """发送 JSON-RPC 错误响应。"""
        resp = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }
        self._write(resp)

    def _write(self, data: dict) -> None:
        """写入 stdout（带刷新）。"""
        line = json.dumps(data, ensure_ascii=False, default=str)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


async def run_mcp_server() -> None:
    """入口函数 —— 启动 MCP Server。"""
    adapter = MCPServerAdapter()
    await adapter.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_mcp_server())
