"""
DAG 编排引擎 API 端点

提供 REST 接口：
- POST /api/v1/orchestrator/parse  — 解析 tool_calls 为 TaskGraph（不执行）
- POST /api/v1/orchestrator/run    — 解析 + 执行 DAG
- GET  /api/v1/orchestrator/runs   — 查询历史执行记录
- POST /api/v1/orchestrator/{run_id}/rollback — 确认执行回滚
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..schemas import APIResponse
from ...orchestrator import (
    parse_tool_calls,
    parse_and_run,
    should_use_dag,
    RollbackGenerator,
)
from ...orchestrator.task import GraphRunStatus
from ...db.dag_runs import save_dag_run, list_dag_runs, get_dag_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orchestrator", tags=["DAG 编排引擎"])


# ============================================================
#  请求/响应模型
# ============================================================

class ToolCallItem(BaseModel):
    """单个工具调用"""
    name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    id: str = Field(default="", description="工具调用 ID（LLM 返回的）")


class ParseRequest(BaseModel):
    """解析请求"""
    tool_calls: list[ToolCallItem] = Field(..., min_length=1, description="工具调用列表")
    session_id: str = Field(default="", description="会话 ID")


class RunRequest(BaseModel):
    """执行请求"""
    tool_calls: list[ToolCallItem] = Field(..., min_length=1, description="工具调用列表")
    session_id: str = Field(default="", description="会话 ID")


class RollbackConfirmRequest(BaseModel):
    """回滚确认请求"""
    task_ids: list[str] = Field(
        default_factory=list,
        description="要回滚的节点 ID 列表（空则回滚全部失败相关节点）",
    )
    confirmed: bool = Field(default=False, description="用户是否确认执行回滚")


# ============================================================
#  API 端点
# ============================================================

@router.post("/parse", response_model=APIResponse, summary="解析 tool_calls 为 DAG")
async def parse_dag(body: ParseRequest) -> APIResponse:
    """
    解析 LLM 返回的 tool_calls 为 TaskGraph（不执行）。
    返回拓扑分层信息和每个节点的分类。
    """
    try:
        tc_list = [tc.model_dump() for tc in body.tool_calls]
        graph = parse_tool_calls(tc_list, session_id=body.session_id)

        return APIResponse(data=graph.to_summary_dict())

    except ValueError as e:
        return APIResponse(code=400, message=str(e))
    except Exception as e:
        logger.error("DAG 解析异常: %s", e, exc_info=True)
        return APIResponse(code=500, message=f"解析失败: {e}")


@router.post("/run", response_model=APIResponse, summary="解析并执行 DAG")
async def run_dag(body: RunRequest) -> APIResponse:
    """
    解析 tool_calls 为 DAG 并执行。
    返回执行记录（含每个节点的状态和结果）。
    """
    try:
        from ...agent.core import AgentContext

        tc_list = [tc.model_dump() for tc in body.tool_calls]

        # 检查是否值得用 DAG
        use_dag = should_use_dag(tc_list)

        if not use_dag:
            return APIResponse(
                code=200,
                data={"skipped": True, "reason": "工具调用数不足或无可并行节点"},
                message="跳过 DAG，建议使用串行执行",
            )

        # 创建临时 AgentContext
        ctx = AgentContext(session_id=body.session_id)

        record = await parse_and_run(tc_list, ctx, session_id=body.session_id)
        record_dict = record.to_dict()

        # 持久化到数据库
        await save_dag_run(record_dict)

        return APIResponse(data=record_dict)

    except ValueError as e:
        return APIResponse(code=400, message=str(e))
    except Exception as e:
        logger.error("DAG 执行异常: %s", e, exc_info=True)
        return APIResponse(code=500, message=f"执行失败: {e}")


@router.get("/runs", response_model=APIResponse, summary="查询 DAG 执行历史")
async def list_runs() -> APIResponse:
    """返回所有 DAG 执行记录摘要（从数据库读取）"""
    recs = await list_dag_runs()
    summaries = []
    for rec in recs:
        summaries.append({
            "run_id": rec["run_id"],
            "session_id": rec.get("session_id", ""),
            "status": rec.get("status", ""),
            "total_nodes": rec.get("total_nodes", 0),
            "success_count": rec.get("success_count", 0),
            "failed_count": rec.get("failed_count", 0),
            "total_execution_ms": rec.get("total_execution_ms", 0),
            "created_at": rec.get("created_at", ""),
        })
    return APIResponse(data=summaries)


@router.get("/runs/{run_id}", response_model=APIResponse, summary="查询 DAG 执行详情")
async def get_run(run_id: str) -> APIResponse:
    """查询指定 DAG 执行记录的详细信息（从数据库读取）"""
    rec = await get_dag_run(run_id)
    if not rec:
        return APIResponse(code=404, message=f"执行记录 {run_id} 不存在")
    return APIResponse(data=rec)


@router.post(
    "/runs/{run_id}/rollback",
    response_model=APIResponse,
    summary="确认执行回滚",
)
async def confirm_rollback(run_id: str, body: RollbackConfirmRequest) -> APIResponse:
    """
    用户确认执行回滚操作。

    仅展示回滚计划，需要用户显式确认后才执行。
    当前版本只返回回滚命令列表供用户手动执行。
    """
    rec = await get_dag_run(run_id)
    if not rec:
        return APIResponse(code=404, message=f"执行记录 {run_id} 不存在")

    if rec.get("status") not in ("partial", "failed"):
        return APIResponse(code=400, message="当前状态无需回滚")

    rollback_commands = rec.get("rollback_commands", [])
    if not rollback_commands:
        return APIResponse(code=200, data={"message": "无可用回滚命令"})

    if not body.confirmed:
        # 展示回滚计划，等待用户确认
        return APIResponse(
            data={
                "rollback_plan": rollback_commands,
                "message": "请确认后执行回滚操作",
                "requires_confirmation": True,
            },
        )

    # 用户已确认 — 执行回滚命令
    # 当前版本：记录回滚确认，命令需通过 execute_command 工具执行
    logger.info("用户确认回滚 run_id=%s, 任务: %s", run_id, body.task_ids)

    executed = []
    for cmd in rollback_commands:
        if body.task_ids and cmd.get("task_id") not in body.task_ids:
            continue
        # 回滚命令标记为待执行
        executed.append({
            "task_id": cmd.get("task_id"),
            "rollback_cmd": cmd.get("rollback_cmd"),
            "status": "pending_execution",
        })

    return APIResponse(
        data={
            "rollback_executed": executed,
            "message": f"已确认 {len(executed)} 个回滚操作，请通过 execute_command 依次执行",
        },
    )


@router.get("/check", response_model=APIResponse, summary="检查是否应使用 DAG")
async def check_dag_applicability(
    tool_calls: str = "",
) -> APIResponse:
    """
    检查给定的 tool_calls 是否适合使用 DAG 并行执行。

    Query 参数:
        tool_calls: JSON 格式的 tool_calls 列表
    """
    import json

    try:
        tc_list = json.loads(tool_calls) if tool_calls else []
    except json.JSONDecodeError:
        return APIResponse(code=400, message="tool_calls JSON 格式错误")

    if not tc_list:
        return APIResponse(code=400, message="tool_calls 不能为空")

    use_dag = should_use_dag(tc_list)
    return APIResponse(data={
        "should_use_dag": use_dag,
        "tool_count": len(tc_list),
    })
