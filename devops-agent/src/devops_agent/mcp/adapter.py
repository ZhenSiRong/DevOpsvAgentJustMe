"""MCP 工具适配器 —— 将外部 MCP Server 的工具包装为本地 MCPTool。

当 Agent 调用 ExternalMCPTool 时，请求被透明转发到对应的 MCPClient，
由 Client 通过 JSON-RPC 调用外部 Server。执行结果再转换回本地格式。
"""

from __future__ import annotations

import logging
from typing import Any

from ..tools.base import MCPTool
from .client import MCPClient

logger = logging.getLogger(__name__)


class ExternalMCPTool(MCPTool):
    """外部 MCP Server 工具的本地代理。

    当 Agent（或 LLM）调用此工具时，请求被转发到对应的 MCP Client，
    由 Client 通过 JSON-RPC 调用外部 Server。

    结果格式转换:
        MCP 格式: { "content": [{"type": "text", "text": "..."}], "isError": false }
        本地格式: { "text": "...", "mcp_result": {...} }
    """

    def __init__(self, client: MCPClient, tool_def: dict[str, Any]):
        self._client = client
        self._raw_def = tool_def

        self.name = tool_def["name"]
        self.description = tool_def.get("description", "")

        # MCP 使用 inputSchema，本地使用 parameters
        schema = tool_def.get("inputSchema", {})
        self.parameters = schema

    @property
    def source_server(self) -> str:
        """返回此工具来源的 MCP Server 名称。"""
        return self._client.name

    async def execute(self, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
        """转发到外部 MCP Server 执行，并转换结果格式。"""
        logger.info(
            "转发 MCP 工具调用: %s -> %s",
            self.name,
            self._client.name,
        )

        result = await self._client.call_tool(self.name, arguments)

        # MCP 响应格式: { "content": [...], "isError": bool }
        # 转换为本地 Agent 友好的格式
        if isinstance(result, dict) and "content" in result:
            texts = []
            images = []

            for item in result.get("content", []):
                item_type = item.get("type", "")
                if item_type == "text":
                    texts.append(item.get("text", ""))
                elif item_type == "image":
                    images.append(item)

            output: dict[str, Any] = {
                "mcp_result": result,
                "text": "\n".join(texts),
            }

            if images:
                output["images"] = images

            if result.get("isError"):
                output["is_error"] = True
                output["error"] = output["text"] or "MCP 工具返回错误"

            return output

        # 非标准格式，直接返回
        return result

    def __repr__(self) -> str:
        return f"<ExternalMCPTool '{self.name}' via {self._client.name}>"
