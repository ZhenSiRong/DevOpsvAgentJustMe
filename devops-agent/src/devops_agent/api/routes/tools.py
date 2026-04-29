"""动态工具管理 API —— 用户运行时注册 MCP Tool

提供动态工具的 CRUD 和测试接口。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...db.dynamic_tools import (
    create_dynamic_tool,
    get_dynamic_tool_by_id,
    get_dynamic_tool_by_name,
    list_dynamic_tools,
    update_dynamic_tool,
    delete_dynamic_tool,
    toggle_dynamic_tool,
)
from ...db.models import DynamicTool
from ...tools import get_registry
from ...tools.dynamic import DynamicMCPTool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["dynamic-tools"])


# ============================================================
#  Pydantic 请求/响应模型
# ============================================================

class ToolConfig(BaseModel):
    """工具配置（根据 tool_type 不同结构）"""
    command: Optional[str] = Field(None, description="Shell 命令模板（shell 类型）")
    timeout: int = Field(30, description="超时秒数")
    shell: str = Field("/bin/bash", description="Shell 解释器路径")
    working_dir: Optional[str] = Field(None, description="工作目录")
    url: Optional[str] = Field(None, description="HTTP URL 模板（http 类型）")
    method: str = Field("GET", description="HTTP 方法")
    headers: dict = Field(default_factory=dict, description="HTTP 请求头")
    body_template: Optional[str] = Field(None, description="HTTP 请求体模板")
    query_params: dict = Field(default_factory=dict, description="HTTP 查询参数模板")


class ToolCreateRequest(BaseModel):
    """注册动态工具请求"""
    name: str = Field(..., description="工具名称（LLM function name）", pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    description: str = Field(..., description="工具功能描述（给 LLM 看）")
    tool_type: str = Field(..., description="工具类型: shell | http | mcp_stdio | mcp_sse")
    config: dict = Field(default_factory=dict, description="工具配置（根据 type 不同结构）")
    parameters: dict = Field(default_factory=dict, description="JSON Schema 参数定义")


class ToolUpdateRequest(BaseModel):
    """更新动态工具请求"""
    description: Optional[str] = Field(None, description="工具描述")
    config: Optional[dict] = Field(None, description="工具配置")
    parameters: Optional[dict] = Field(None, description="JSON Schema 参数定义")
    is_active: Optional[bool] = Field(None, description="是否启用")


class ToolResponse(BaseModel):
    """工具响应"""
    id: int
    name: str
    description: str
    tool_type: str
    config: dict
    schema: dict = Field(alias="schema_json")
    is_active: bool
    created_by: str
    created_at: str
    updated_at: str


class ToolTestRequest(BaseModel):
    """测试工具请求"""
    arguments: dict = Field(default_factory=dict, description="调用参数")


class ToolListResponse(BaseModel):
    """工具列表响应"""
    items: list[ToolResponse]
    total: int


# ============================================================
#  API 端点
# ============================================================

@router.post("", response_model=ToolResponse, status_code=status.HTTP_201_CREATED)
async def register_tool(request: ToolCreateRequest):
    """
    注册新的动态工具。

    工具名称不能与内置工具重名（如 disk_usage、execute_command 等）。
    注册成功后，Agent 立即可以使用该工具。
    """
    # 检查名称是否与内置工具冲突
    registry = get_registry()
    if registry.is_builtin(request.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"工具名称 '{request.name}' 与内置工具冲突，请更换名称",
        )

    # 检查是否已存在同名动态工具
    existing = await get_dynamic_tool_by_name(request.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"动态工具 '{request.name}' 已存在",
        )

    try:
        tool = await create_dynamic_tool(
            name=request.name,
            description=request.description,
            tool_type=request.tool_type,
            config=request.config,
            schema_json=request.parameters,
            created_by="api",
        )

        # 立即注册到 Registry（热加载）
        dynamic_tool = DynamicMCPTool(
            name=tool.name,
            description=tool.description,
            parameters=tool.schema_json,
            tool_type=tool.tool_type,
            config=tool.config,
        )
        registry._tools[tool.name] = dynamic_tool
        logger.info("动态工具 API 注册并热加载: %s", tool.name)

        return tool.to_dict()
    except Exception as e:
        logger.error("注册动态工具失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"注册失败: {str(e)}",
        )


@router.get("", response_model=ToolListResponse)
async def list_tools(active_only: bool = False):
    """
    列出所有动态工具。

    - active_only=true: 只返回启用的工具
    - active_only=false: 返回全部（包括禁用的）
    """
    tools = await list_dynamic_tools(active_only=active_only)
    return ToolListResponse(
        items=[t.to_dict() for t in tools],
        total=len(tools),
    )


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: int):
    """获取指定动态工具的详情。"""
    tool = await get_dynamic_tool_by_id(tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工具 ID {tool_id} 不存在",
        )
    return tool.to_dict()


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(tool_id: int, request: ToolUpdateRequest):
    """
    更新动态工具配置。

    注意：更新后会重新加载工具到 Registry。
    """
    tool = await get_dynamic_tool_by_id(tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工具 ID {tool_id} 不存在",
        )

    try:
        updated = await update_dynamic_tool(
            tool_id=tool_id,
            description=request.description,
            config=request.config,
            schema_json=request.parameters,
            is_active=request.is_active,
        )

        # 如果工具处于启用状态，重新加载到 Registry
        if updated and updated.is_active:
            registry = get_registry()
            dynamic_tool = DynamicMCPTool(
                name=updated.name,
                description=updated.description,
                parameters=updated.schema_json,
                tool_type=updated.tool_type,
                config=updated.config,
            )
            registry._tools[updated.name] = dynamic_tool
            logger.info("动态工具已更新并重新加载: %s", updated.name)
        elif updated and not updated.is_active:
            # 禁用时从 Registry 移除
            registry = get_registry()
            if updated.name in registry._tools and not registry.is_builtin(updated.name):
                del registry._tools[updated.name]
                logger.info("动态工具已禁用并移除: %s", updated.name)

        return updated.to_dict()
    except Exception as e:
        logger.error("更新动态工具失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新失败: {str(e)}",
        )


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(tool_id: int):
    """删除动态工具。"""
    tool = await get_dynamic_tool_by_id(tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工具 ID {tool_id} 不存在",
        )

    # 从 Registry 移除
    registry = get_registry()
    if tool.name in registry._tools and not registry.is_builtin(tool.name):
        del registry._tools[tool.name]
        logger.info("动态工具已从 Registry 移除: %s", tool.name)

    deleted = await delete_dynamic_tool(tool_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除失败",
        )


@router.post("/{tool_id}/toggle", response_model=ToolResponse)
async def toggle_tool(tool_id: int):
    """切换动态工具的启用/禁用状态。"""
    tool = await get_dynamic_tool_by_id(tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工具 ID {tool_id} 不存在",
        )

    updated = await toggle_dynamic_tool(tool_id)

    # 同步到 Registry
    registry = get_registry()
    if updated.is_active:
        dynamic_tool = DynamicMCPTool(
            name=updated.name,
            description=updated.description,
            parameters=updated.schema_json,
            tool_type=updated.tool_type,
            config=updated.config,
        )
        registry._tools[updated.name] = dynamic_tool
        logger.info("动态工具已启用: %s", updated.name)
    else:
        if updated.name in registry._tools and not registry.is_builtin(updated.name):
            del registry._tools[updated.name]
            logger.info("动态工具已禁用: %s", updated.name)

    return updated.to_dict()


@router.post("/{tool_id}/test")
async def test_tool(tool_id: int, request: ToolTestRequest):
    """
    测试动态工具（直接执行，不经过 LLM）。

    用于调试工具配置是否正确。
    """
    tool = await get_dynamic_tool_by_id(tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工具 ID {tool_id} 不存在",
        )

    if not tool.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="工具已禁用，无法测试",
        )

    try:
        dynamic_tool = DynamicMCPTool(
            name=tool.name,
            description=tool.description,
            parameters=tool.schema_json,
            tool_type=tool.tool_type,
            config=tool.config,
        )

        # 创建 mock context
        class MockContext:
            tool_round = 0
            execution_count = 0
            probe_call_count = 0

        result = await dynamic_tool.execute(request.arguments, MockContext())
        return {
            "tool_name": tool.name,
            "tool_type": tool.tool_type,
            "arguments": request.arguments,
            "result": result,
            "success": not result.get("is_error", False),
        }
    except Exception as e:
        logger.error("测试动态工具失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试失败: {str(e)}",
        )


# ============================================================
#  注册中心工具列表（内置 + 动态 + MCP）
# ============================================================

class RegistryToolItem(BaseModel):
    """注册中心中的单个工具信息"""
    name: str
    description: str
    is_builtin: bool
    source: str  # "builtin" | "dynamic" | "mcp"
    parameters: dict


class RegistryToolsResponse(BaseModel):
    """注册中心工具列表响应"""
    tools: list[RegistryToolItem]
    total: int
    builtin_count: int
    dynamic_count: int
    mcp_count: int


@router.get("/registry", response_model=RegistryToolsResponse)
async def list_registry_tools():
    """
    列出注册中心中所有已注册的工具。

    包括：
    - 内置工具（代码中注册的 ProbeTool）
    - 动态工具（从数据库加载的 DynamicMCPTool）
    - MCP Server 工具（外部 MCP Server 连接后注册的 ExternalMCPTool）

    前端 MCP 管理页面用此接口展示「已注册工具」全景。
    """
    registry = get_registry()

    # 收集 MCP Server 注册的工具名称（用于判断来源）
    mcp_tool_names: set[str] = set()
    for client in registry._mcp_clients.values():
        for tool_def in getattr(client, "tools", []):
            mcp_tool_names.add(tool_def.get("name", ""))

    tools: list[RegistryToolItem] = []
    builtin_count = 0
    dynamic_count = 0
    mcp_count = 0

    for name in registry.list_names():
        tool = registry.get(name)
        if tool is None:
            continue

        is_builtin = registry.is_builtin(name)
        is_mcp = name in mcp_tool_names

        if is_builtin:
            builtin_count += 1
        elif is_mcp:
            mcp_count += 1
        else:
            dynamic_count += 1

        source = "builtin" if is_builtin else ("mcp" if is_mcp else "dynamic")
        tools.append(RegistryToolItem(
            name=name,
            description=tool.description,
            is_builtin=is_builtin,
            source=source,
            parameters=tool.parameters if isinstance(tool.parameters, dict) else {},
        ))

    return RegistryToolsResponse(
        tools=tools,
        total=len(tools),
        builtin_count=builtin_count,
        dynamic_count=dynamic_count,
        mcp_count=mcp_count,
    )
