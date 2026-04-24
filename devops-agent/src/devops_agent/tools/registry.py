"""
MCP 工具注册中心 —— 统一管理所有可用工具的注册、查询和执行

职责：
1. 维护 name -> MCPTool 实例的映射表
2. 提供工具发现（list）和工具获取（get）接口
3. 统一执行入口（含异常包装和日志）
4. 生成 LLM function calling 所需的工具定义列表
5. 支持动态工具注册（运行时从数据库加载）

线程安全：当前为单线程 asyncio 环境，无需额外锁。
"""

from __future__ import annotations

import logging
from typing import Any

from ..agent.llm_client import ToolDefinition
from .base import MCPTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    工具注册中心 —— 单例模式。

    使用示例：
        registry = ToolRegistry()
        registry.register(DiskUsageTool())
        tool = registry.get("disk_usage")
        result = await registry.execute("disk_usage", {"path": "/"}, ctx)
    """

    _instance: "ToolRegistry | None" = None
    _tools: dict[str, MCPTool]
    _builtin_names: set[str]  # 内置工具名称集合（防覆盖）

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._builtin_names = set()
        return cls._instance

    def register(self, tool: MCPTool) -> None:
        """
        注册一个工具实例。

        如果 name 已存在，覆盖注册并发出警告（通常意味着重复导入）。
        """
        if tool.name in self._tools:
            logger.warning(
                "工具 %s 重复注册，覆盖旧实例", tool.name
            )
        self._tools[tool.name] = tool
        logger.debug("工具已注册: %s", tool.name)

    def register_builtin(self, tool: MCPTool) -> None:
        """注册内置工具，并标记为不可被动态工具覆盖。"""
        self.register(tool)
        self._builtin_names.add(tool.name)

    def unregister(self, name: str) -> bool:
        """注销指定名称的工具（内置工具不可注销）。"""
        if name in self._builtin_names:
            logger.warning("尝试注销内置工具 %s，已拒绝", name)
            return False
        if name in self._tools:
            del self._tools[name]
            logger.info("工具已注销: %s", name)
            return True
        return False

    def get(self, name: str) -> MCPTool | None:
        """按名称获取工具实例"""
        return self._tools.get(name)

    def list_tools(self) -> list[MCPTool]:
        """返回所有已注册工具的列表"""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """返回所有已注册工具的名称列表"""
        return list(self._tools.keys())

    def is_builtin(self, name: str) -> bool:
        """判断工具是否为内置工具。"""
        return name in self._builtin_names

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """
        生成 LLM function calling 所需的 ToolDefinition 列表。

        供 agent/core.py 构建 system prompt 时调用。
        """
        definitions = []
        for tool in self._tools.values():
            definitions.append(
                ToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.parameters,
                )
            )
        return definitions

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        ctx: Any,
    ) -> dict[str, Any]:
        """
        统一执行入口。

        执行流程：
        1. 查找工具
        2. 调用 tool.execute()
        3. 异常捕获并包装为标准化错误格式

        Args:
            name: 工具名称
            arguments: 参数字典
            ctx: AgentContext（运行时上下文）

        Returns:
            工具执行结果 dict；出错时返回 {"error": "...", "is_error": True}
        """
        tool = self.get(name)
        if tool is None:
            return {"error": f"未知工具: {name}", "is_error": True}

        try:
            return await tool.execute(arguments, ctx)
        except Exception as e:
            logger.error("工具 %s 执行异常: %s", name, e, exc_info=True)
            return {
                "error": f"工具执行异常: {type(e).__name__}: {e}",
                "is_error": True,
            }

    async def load_dynamic_tools(self) -> int:
        """
        从数据库加载所有启用的动态工具并注册到 Registry。

        Returns:
            加载的动态工具数量。
        """
        from ..db.dynamic_tools import list_dynamic_tools
        from .dynamic import DynamicMCPTool

        tools = await list_dynamic_tools(active_only=True)
        count = 0
        for dt in tools:
            # 检查名称冲突（不能与内置工具同名）
            if dt.name in self._builtin_names:
                logger.warning(
                    "动态工具 %s 与内置工具重名，跳过加载", dt.name
                )
                continue

            try:
                tool = DynamicMCPTool(
                    name=dt.name,
                    description=dt.description,
                    parameters=dt.schema_json,
                    tool_type=dt.tool_type,
                    config=dt.config,
                )
                # 直接放入 _tools，不标记为 builtin
                self._tools[tool.name] = tool
                count += 1
                logger.debug("动态工具已加载: %s", dt.name)
            except Exception as e:
                logger.error("加载动态工具 %s 失败: %s", dt.name, e)

        logger.info("从数据库加载 %d 个动态工具", count)
        return count

    def clear(self) -> None:
        """清空所有注册（主要用于测试隔离）"""
        self._tools.clear()
        self._builtin_names.clear()
        logger.info("工具注册中心已清空")

    def __repr__(self) -> str:
        return f"<ToolRegistry tools={self.list_names()}>"


# ============================================================
#  全局快捷函数（减少 import 链长度）
# ============================================================

_default_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """获取全局默认注册中心实例"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def register_tool(tool: MCPTool) -> None:
    """全局快捷注册函数"""
    get_registry().register(tool)


def register_builtin_tool(tool: MCPTool) -> None:
    """全局快捷注册内置工具函数"""
    get_registry().register_builtin(tool)


def get_tool(name: str) -> MCPTool | None:
    """全局快捷获取函数"""
    return get_registry().get(name)


def list_tools() -> list[MCPTool]:
    """全局快捷列出函数"""
    return get_registry().list_tools()


def get_tool_definitions() -> list[ToolDefinition]:
    """全局快捷生成 LLM 工具定义列表"""
    return get_registry().get_tool_definitions()


async def dispatch_tool(name: str, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """全局快捷执行函数 —— 替代 agent/core.py 中的 dispatch_tool_call"""
    return await get_registry().execute(name, arguments, ctx)


__all__ = [
    "ToolRegistry",
    "get_registry",
    "register_tool",
    "register_builtin_tool",
    "get_tool",
    "list_tools",
    "get_tool_definitions",
    "dispatch_tool",
]
