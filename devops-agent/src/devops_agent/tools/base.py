"""
MCP 工具基类 —— DevOps Agent 的工具插件化基础设施

设计原则：
1. 每个工具是一个独立的 MCPTool 子类，自包含定义和执行逻辑
2. 工具通过 ToolRegistry 注册，Agent 引擎从注册中心动态获取工具列表
3. 新增工具只需：继承 MCPTool → 实现 execute → 注册 → 自动生效
4. 兼容现有探针模块（probe/）和安全执行器（safety/executor），不做重写

对应赛题要求：MCP工具插件化 —— 实现适配层 + 工具注册中心 + 内置插件封装
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent.core import AgentContext

logger = logging.getLogger(__name__)


class MCPTool(ABC):
    """
    MCP（Model Context Protocol）工具抽象基类。

    所有 DevOps Agent 可调用的能力（探针、执行器、外部集成）
    都必须继承此类并注册到 ToolRegistry。

    Attributes:
        name: 工具标识符（LLM function calling 中使用）
        description: 工具功能描述（注入 LLM system prompt）
        parameters: JSON Schema 格式的参数定义
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}

    @abstractmethod
    async def execute(self, arguments: dict[str, Any], ctx: "AgentContext") -> dict[str, Any]:
        """
        执行工具逻辑。

        Args:
            arguments: LLM 提供的参数（已按 parameters schema 解析为 dict）
            ctx: 当前 Agent 运行时上下文（含 session_id、轮次统计等）

        Returns:
            工具执行结果，必须是可 JSON 序列化的 dict
        """
        ...

    def to_llm_definition(self) -> dict[str, Any]:
        """
        转换为 LLM function calling 格式的工具定义。

        Returns OpenAI-compatible tool schema:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": {...}
            }
        }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __repr__(self) -> str:
        return f"<MCPTool {self.name}>"


class ProbeTool(MCPTool):
    """
    探针类工具基类 —— 只读操作，无副作用。

    自动增加 ctx.probe_call_count 统计。
    """

    async def execute(self, arguments: dict[str, Any], ctx: "AgentContext") -> dict[str, Any]:
        ctx.probe_call_count += 1
        logger.info("探针调用 #%d: %s(%s)", ctx.probe_call_count, self.name, arguments)
        result = await self._probe(arguments, ctx)
        return self._format_result(result)

    @abstractmethod
    async def _probe(self, arguments: dict[str, Any], ctx: "AgentContext") -> Any:
        """子类实现具体的探针逻辑"""
        ...

    def _format_result(self, result: Any) -> dict[str, Any]:
        """将探针结果格式化为 LLM 友好的字典"""
        if hasattr(result, "to_dict"):
            return result.to_dict()
        if isinstance(result, dict):
            return result
        if hasattr(result, "__iter__") and not isinstance(result, (str, bytes)):
            items = []
            for r in result:
                items.append(r.to_dict() if hasattr(r, "to_dict") else r)
            return {"items": items, "count": len(items)}
        return {"raw": str(result)}


class ExecutorTool(MCPTool):
    """
    执行类工具基类 —— 可能修改系统状态，受安全层约束。

    自动增加 ctx.execution_count 统计。
    """

    async def execute(self, arguments: dict[str, Any], ctx: "AgentContext") -> dict[str, Any]:
        ctx.execution_count += 1
        logger.info("执行调用 #%d: %s(%s)", ctx.execution_count, self.name, arguments)
        return await self._execute(arguments, ctx)

    @abstractmethod
    async def _execute(self, arguments: dict[str, Any], ctx: "AgentContext") -> dict[str, Any]:
        """子类实现具体的执行逻辑"""
        ...


__all__ = ["MCPTool", "ProbeTool", "ExecutorTool"]
