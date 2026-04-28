"""MCP Server 管理 API —— 外部 MCP Server 的连接配置与生命周期管理

端点：
- GET    /api/v1/mcp/env-check            环境依赖检测
- POST   /api/v1/mcp/servers/import       JSON 批量导入（Claude Desktop 格式）
- GET    /api/v1/mcp/servers              列出所有配置
- POST   /api/v1/mcp/servers              新增配置
- GET    /api/v1/mcp/servers/{id}         获取单个配置
- PUT    /api/v1/mcp/servers/{id}         更新配置
- DELETE /api/v1/mcp/servers/{id}         删除配置
- POST   /api/v1/mcp/servers/{id}/connect    连接 Server
- POST   /api/v1/mcp/servers/{id}/disconnect 断开 Server
- POST   /api/v1/mcp/servers/{id}/ping       心跳测试
- GET    /api/v1/mcp/servers/{id}/tools      列出 Server 工具
- GET    /api/v1/mcp/connected             列出已连接状态
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...db.mcp_servers import (
    create_mcp_server,
    get_mcp_server_by_id,
    list_mcp_servers as db_list_mcp_servers,
    update_mcp_server,
    delete_mcp_server,
    toggle_mcp_server,
)
from ...tools.registry import get_registry
from ..schemas import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mcp", tags=["MCP"])


# ============================================================
#  Pydantic 请求/响应模型
# ============================================================


class MCPServerCreateRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=64, description="Server 唯一标识")
    name: str = Field(..., min_length=1, max_length=128, description="显示名称")
    transport: str = Field(..., pattern="^(stdio|sse)$", description="传输类型")
    command: str | None = Field(None, description="stdio 命令")
    args: list[str] = Field(default_factory=list, description="命令参数")
    env: dict[str, str] = Field(default_factory=dict, description="环境变量")
    url: str | None = Field(None, description="sse URL")
    cwd: str | None = Field(None, description="工作目录")


class MCPServerUpdateRequest(BaseModel):
    name: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    cwd: str | None = None


class MCPImportRequest(BaseModel):
    json_text: str = Field(..., description="Claude Desktop 格式的 JSON 配置文本")


# ============================================================
#  配置 CRUD
# ============================================================


@router.get("/servers", response_model=APIResponse)
async def list_servers():
    """列出所有 MCP Server 配置（含连接状态）。"""
    configs = await db_list_mcp_servers(active_only=False)
    registry = get_registry()
    connected = {s["id"]: s for s in registry.list_mcp_servers()}

    items = []
    for cfg in configs:
        item = cfg.to_dict()
        conn = connected.get(cfg.id)
        item["connected"] = conn is not None
        item["tool_count"] = conn["tool_count"] if conn else 0
        items.append(item)

    return APIResponse(data=items)


@router.post("/servers", response_model=APIResponse)
async def add_server(req: MCPServerCreateRequest):
    """新增 MCP Server 配置（仅保存，不自动连接）。"""
    existing = await get_mcp_server_by_id(req.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"MCP Server '{req.id}' 已存在")

    cfg = await create_mcp_server(
        server_id=req.id,
        name=req.name,
        transport=req.transport,
        command=req.command,
        args=req.args,
        env=req.env,
        url=req.url,
        cwd=req.cwd,
    )
    return APIResponse(data=cfg.to_dict(), message="MCP Server 配置已保存")


@router.get("/servers/{server_id}", response_model=APIResponse)
async def get_server(server_id: str):
    """获取单个 MCP Server 配置。"""
    cfg = await get_mcp_server_by_id(server_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")

    registry = get_registry()
    conn = registry.get_mcp_client(server_id)
    item = cfg.to_dict()
    item["connected"] = conn is not None
    item["tool_count"] = len(conn.tools) if conn else 0
    return APIResponse(data=item)


@router.put("/servers/{server_id}", response_model=APIResponse)
async def modify_server(server_id: str, req: MCPServerUpdateRequest):
    """更新 MCP Server 配置。"""
    existing = await get_mcp_server_by_id(server_id)
    if not existing:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")

    cfg = await update_mcp_server(
        server_id=server_id,
        name=req.name,
        command=req.command,
        args=req.args,
        env=req.env,
        url=req.url,
        cwd=req.cwd,
    )
    return APIResponse(data=cfg.to_dict(), message="MCP Server 配置已更新")


@router.delete("/servers/{server_id}", response_model=APIResponse)
async def remove_server(server_id: str):
    """删除 MCP Server 配置（如果已连接会先断开）。"""
    existing = await get_mcp_server_by_id(server_id)
    if not existing:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")

    # 如果已连接，先断开
    registry = get_registry()
    if registry.get_mcp_client(server_id):
        await registry.disconnect_mcp_server(server_id)

    deleted = await delete_mcp_server(server_id)
    return APIResponse(
        data={"deleted": deleted},
        message="MCP Server 配置已删除",
    )


# ============================================================
#  连接生命周期管理
# ============================================================


@router.post("/servers/{server_id}/connect", response_model=APIResponse)
async def connect_server(server_id: str):
    """连接指定 MCP Server（从配置加载并建立连接）。"""
    cfg = await get_mcp_server_by_id(server_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")

    registry = get_registry()
    if registry.get_mcp_client(server_id):
        return APIResponse(
            data={"tool_names": []},
            message="MCP Server 已连接",
        )

    config_dict = {
        "id": cfg.id,
        "name": cfg.name,
        "transport": cfg.transport,
        "command": cfg.command,
        "args": cfg.args,
        "env": cfg.env,
        "url": cfg.url,
        "cwd": cfg.cwd,
    }

    try:
        tool_names = await registry.connect_mcp_server(config_dict)
        return APIResponse(
            data={
                "server_id": server_id,
                "tool_names": tool_names,
                "tool_count": len(tool_names),
            },
            message=f"已连接，注册 {len(tool_names)} 个工具",
        )
    except Exception as e:
        logger.error("连接 MCP Server '%s' 失败: %s", server_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"连接失败: {type(e).__name__}: {e}",
        )


@router.post("/servers/{server_id}/disconnect", response_model=APIResponse)
async def disconnect_server(server_id: str):
    """断开指定 MCP Server 连接。"""
    registry = get_registry()
    if not registry.get_mcp_client(server_id):
        return APIResponse(message="MCP Server 未连接")

    removed = await registry.disconnect_mcp_server(server_id)
    return APIResponse(
        data={"removed_tools": removed, "count": len(removed)},
        message=f"已断开，注销 {len(removed)} 个工具",
    )


@router.post("/servers/{server_id}/ping", response_model=APIResponse)
async def ping_server(server_id: str):
    """对指定 MCP Server 发送心跳。"""
    registry = get_registry()
    ok = await registry.ping_mcp_server(server_id)
    return APIResponse(
        data={"alive": ok},
        message="心跳正常" if ok else "无响应",
    )


@router.get("/servers/{server_id}/tools", response_model=APIResponse)
async def list_server_tools(server_id: str):
    """获取指定 MCP Server 的工具列表（需已连接）。"""
    registry = get_registry()
    client = registry.get_mcp_client(server_id)
    if not client:
        raise HTTPException(status_code=404, detail="MCP Server 未连接")

    return APIResponse(
        data={
            "server_id": server_id,
            "tools": client.list_tools(),
        },
    )


@router.get("/connected", response_model=APIResponse)
async def list_connected():
    """列出当前已连接的 MCP Server 状态。"""
    registry = get_registry()
    servers = registry.list_mcp_servers()
    return APIResponse(data=servers)


# ============================================================
#  环境依赖检测
# ============================================================


def _check_binary(name: str, version_flag: str = "--version") -> dict[str, Any]:
    """检测单个二进制文件的可用性和版本。"""
    path = shutil.which(name)
    if not path:
        return {"name": name, "available": False, "version": None, "path": None}

    try:
        result = subprocess.run(
            [name, version_flag],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = (result.stdout.strip() or result.stderr.strip())[:200]
    except Exception:
        version = None

    return {"name": name, "available": True, "version": version, "path": path}


@router.get("/env-check", response_model=APIResponse, summary="检测 MCP 运行环境依赖")
async def env_check():
    """
    检测当前系统是否具备运行各类 MCP Server 的依赖。

    返回每个依赖的可用状态、版本号和路径。
    龙芯(loongarch64)环境下 node/npm/npx/uv 通常不可用，
    建议优先使用内置 Python MCP Server（零外部依赖）。
    """
    checks = [
        _check_binary("python3"),
        _check_binary("python"),
        _check_binary("pip3"),
        _check_binary("node"),
        _check_binary("npm"),
        _check_binary("npx"),
        _check_binary("uv"),
    ]

    # 标记哪些 server 类型可用
    python_ready = any(c["available"] for c in checks if c["name"] in ("python3", "python"))
    node_ready = any(c["available"] for c in checks if c["name"] == "node")
    npm_ready = any(c["available"] for c in checks if c["name"] == "npm")

    return APIResponse(data={
        "dependencies": checks,
        "summary": {
            "python_ready": python_ready,
            "node_ready": node_ready,
            "npm_ready": npm_ready,
            "recommended_transport": "stdio" if python_ready else None,
        },
        "note": "龙芯(loongarch64)架构下通常无 node/npm 预编译包，"
                "建议使用内置 Python MCP Server（纯标准库实现）。",
    })


# ============================================================
#  JSON 批量导入（Claude Desktop 格式）
# ============================================================


def _detect_builtin_server(command: str, args: list[str]) -> dict[str, Any] | None:
    """
    检测是否为已知的外部 MCP Server，返回适配建议。
    如果检测到是 npm 包，提示龙芯上不可用。
    """
    if not command:
        return None

    cmd_lower = command.lower()
    full = " ".join([command] + args).lower()

    # npm / npx / node 类
    if any(x in cmd_lower for x in ("npx", "npm", "node")):
        return {
            "type": "npm",
            "compatible": False,
            "reason": "需要 Node.js，龙芯(loongarch64)通常无预编译包",
            "suggestion": "使用内置 Python MCP Server 替代，或通过 pip 安装纯 Python 实现",
        }

    # uv 类
    if "uv" in cmd_lower:
        return {
            "type": "uv",
            "compatible": False,
            "reason": "需要 uv，龙芯(loongarch64)通常无预编译包",
            "suggestion": "使用 python3 直接运行内置 MCP Server",
        }

    # Python 类
    if any(x in cmd_lower for x in ("python", "python3")):
        return {
            "type": "python",
            "compatible": True,
            "reason": "纯 Python 实现，龙芯兼容",
            "suggestion": None,
        }

    return {
        "type": "unknown",
        "compatible": None,
        "reason": "未知命令类型",
        "suggestion": "请手动验证该命令在目标架构上的可用性",
    }


@router.post("/servers/import", response_model=APIResponse, summary="JSON 批量导入 MCP Server")
async def import_servers(req: MCPImportRequest):
    """
    从 Claude Desktop 格式的 JSON 配置批量导入 MCP Server。

    支持格式::

        {
          "mcpServers": {
            "server-id": {
              "command": "python3",
              "args": ["/path/to/server.py"],
              "env": {"KEY": "value"}
            }
          }
        }

    对每个 Server：
    - 检测命令类型（python/npm/uv/unknown）
    - 标记龙芯兼容性
    - 保存到数据库（transport 固定为 stdio）
    """
    try:
        data = json.loads(req.json_text)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"JSON 解析失败: {e}")

    mcp_servers = data.get("mcpServers") or data.get("mcp_servers")
    if not isinstance(mcp_servers, dict):
        raise HTTPException(
            status_code=422,
            detail="JSON 中未找到 'mcpServers' 或 'mcp_servers' 对象",
        )

    results = []
    errors = []
    for server_id, cfg in mcp_servers.items():
        if not isinstance(cfg, dict):
            errors.append({"id": server_id, "error": "配置必须是对象"})
            continue

        command = cfg.get("command", "")
        args = cfg.get("args", [])
        env = cfg.get("env", {})

        # 兼容性检测
        compat = _detect_builtin_server(command, args)

        # 生成显示名称
        name = cfg.get("name") or server_id.replace("_", " ").replace("-", " ").title()

        try:
            existing = await get_mcp_server_by_id(server_id)
            if existing:
                # 已存在则更新
                await update_mcp_server(
                    server_id=server_id,
                    name=name,
                    command=command,
                    args=args,
                    env=env,
                )
                results.append({
                    "id": server_id,
                    "action": "updated",
                    "name": name,
                    "compat": compat,
                })
            else:
                await create_mcp_server(
                    server_id=server_id,
                    name=name,
                    transport="stdio",
                    command=command,
                    args=args,
                    env=env,
                )
                results.append({
                    "id": server_id,
                    "action": "created",
                    "name": name,
                    "compat": compat,
                })
        except Exception as e:
            errors.append({"id": server_id, "error": str(e)})

    return APIResponse(data={
        "imported": results,
        "errors": errors,
        "total": len(mcp_servers),
        "success_count": len(results),
        "error_count": len(errors),
    }, message=f"导入完成: {len(results)} 成功, {len(errors)} 失败")
