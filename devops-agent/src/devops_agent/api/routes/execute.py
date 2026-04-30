"""
路由 3/7：安全命令执行

POST /api/v1/execute — Agent 修改 OS 状态的唯一入口

安全机制：
1. 安全校验器（rules.py + validator.py）前置拦截
2. 白名单前缀匹配
3. sudo -u devops-runner 最小权限执行
4. 超时自动 kill（默认 30s）
5. 每次执行写入审计表
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ...safety.executor import (
    execute,
    execute_unrestricted,
    ExecutionStatus,
)
from ..schemas import APIResponse, ExecuteRequest, ExecuteResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["命令执行"])


@router.post("/execute", response_model=APIResponse, summary="安全执行命令")
async def execute_command(
    body: ExecuteRequest,
    request: Request,
) -> APIResponse:
    """
    安全地执行一条 shell 命令。

    执行流程：
    1. 安全校验 → 危险命令直接拦截 (BLOCKED)
    2. 白名单检查 → 不在白名单返回 REJECTED
    3. sudo -u devops-runner 以最小权限用户执行
    4. 超时控制（可配，默认 30s）→ 超时强制 kill
    5. 结果收集 + 审计记录写入 DB

    支持 dry_run 模式：只做校验不实际执行。
    """
    start_time = time.monotonic()
    client_ip = request.client.host if request.client else "unknown"

    # ---- dry_run：只校验不执行 ----
    if body.dry_run:
        from ...safety.validator import validate_command
        validation = validate_command(body.command)

        # 同时检查白名单
        from ...safety.executor import is_command_allowed
        whitelisted, wl_reason = is_command_allowed(body.command)

        elapsed = (time.monotonic() - start_time) * 1000
        return APIResponse(
            data={
                "dry_run": True,
                "command": body.command,
                "security_result": validation.result.value,
                "security_reason": validation.reason,
                "whitelisted": whitelisted,
                "whitelist_reason": wl_reason,
                "would_execute": (
                    validation.result.value != "BLOCKED" and whitelisted
                ),
                "elapsed_ms": round(elapsed, 2),
            },
        )

    # ---- 幂等检查 ----
    from ...safety.idempotency import get_idempotency_guard, OperationState
    ikey = body.idempotency_key
    if ikey:
        guard = get_idempotency_guard()
        existing = await guard.check(ikey)
        if existing and existing.state in (
            OperationState.SUCCESS,
            OperationState.FAILED,
            OperationState.BLOCKED,
            OperationState.TIMEDOUT,
        ):
            logger.info("幂等命中: key=%s state=%s", ikey, existing.state)
            return APIResponse(
                data={**(existing.result or {}), "idempotent": True, "cached_state": existing.state},
                message=f"幂等返回（状态: {existing.state}）",
            )

    # ---- 真实执行 ----
    # 运维者模式：需显式 X-Operator-Mode header 标记，仍过安全校验但跳过白名单
    # 普通/Agent 模式：同时经过安全校验 + 白名单检查（默认更安全）
    is_operator_mode = request.headers.get("X-Operator-Mode", "").lower() == "true"

    try:
        if is_operator_mode:
            result = await execute_unrestricted(
                command=body.command,
                timeout=body.timeout,
            )
        else:
            # 默认走完整安全链路：安全校验 + 白名单
            from ...safety.executor import execute as execute_safe
            result = await execute_safe(
                command=body.command,
                timeout=body.timeout,
            )

        # 写入审计日志（异步，不阻塞响应；失败时记录错误日志而非静默吞掉）
        import asyncio
        audit_task = asyncio.create_task(
            _audit_log_async(result, client_ip, session_id=body.session_id or "")
        )
        audit_task.add_done_callback(_audit_callback)

        response_data = {
            "command": result.command,
            "status": result.status.value,
            "exit_code": result.exit_code,
            "stdout": result.stdout[:5000] if result.stdout else "",  # 截断防止过大
            "stderr": result.stderr[:2000] if result.stderr else "",
            "error_message": result.error_message,
            "execution_time_ms": result.execution_time_ms,
            "executed_by": result.executed_by,
            "security_check": result.security_check,
        }

        # 幂等结果缓存
        if ikey:
            state_map = {
                "SUCCESS": OperationState.SUCCESS,
                "FAILED": OperationState.FAILED,
                "TIMEOUT": OperationState.TIMEDOUT,
                "REJECTED": OperationState.FAILED,
                "BLOCKED": OperationState.BLOCKED,
            }
            await guard.mark_complete(
                ikey,
                state_map.get(result.status.value, OperationState.FAILED),
                response_data,
            )

        # 根据状态决定 HTTP 状态码
        http_code = _map_status_to_http(result.status)

        return APIResponse(
            data=response_data,
            message=f"执行{result.status.value}: {result.error_message or '成功'}",
        )

    except Exception as e:
        logger.error("执行引擎异常: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"执行引擎内部错误: {type(e).__name__}: {e}",
        )


def _map_status_to_http(status: ExecutionStatus) -> int:
    """将执行状态映射到 HTTP 状态码"""
    mapping = {
        ExecutionStatus.SUCCESS: 200,
        ExecutionStatus.FAILED: 200,       # 命令失败但请求成功处理
        ExecutionStatus.TIMEOUT: 504,      # Gateway Timeout
        ExecutionStatus.REJECTED: 403,     # Forbidden
        ExecutionStatus.BLOCKED: 403,      # Forbidden（更严重的安全拦截）
    }
    return mapping.get(status, 500)


async def _audit_log_async(result, client_ip: str, session_id: str = ""):
    """异步写入审计日志到数据库（非阻塞）"""
    try:
        from ...db.audit import append_audit_log

        # 状态映射：ExecutionStatus -> audit_logs.status
        status_map = {
            "SUCCESS": "ok",
            "FAILED": "error",
            "TIMEOUT": "error",
            "REJECTED": "warning",
            "BLOCKED": "blocked",
        }
        audit_status = status_map.get(result.status.value, "ok")

        # 安全校验结果提取
        security_result = None
        if result.security_check:
            security_result = result.security_check.get("result")

        await append_audit_log(
            session_id=session_id or "system",
            phase="execution",
            content=result.command[:500],
            status=audit_status,
            security_result=security_result,
            blocked_reason=result.error_message[:500] if result.error_message else None,
            raw_output=(result.stdout[:1000] if result.stdout else ""),
            duration_ms=int(result.execution_time_ms),
            command=result.command[:500],
            exit_code=result.exit_code,
            executed_by=result.executed_by,
            source_ip=client_ip,
        )
        logger.info("审计记录已落库: cmd=%s status=%s by=%s",
                     result.command[:50], result.status.value, result.executed_by)
    except Exception as e:
        # 审计写入失败：提升日志级别为 ERROR（原 WARNING 会因日志级别过滤被忽略）
        logger.error("审计日志写入失败: session=%s cmd=%s error=%s",
                      session_id, result.command[:50] if result else "N/A", e)


def _audit_callback(task):
    """审计异步任务的 done callback：捕获未处理的异常，防止静默丢失"""
    if not task.cancelled():
        exc = task.exception()
        if exc:
            logger.error("审计日志任务异常(未被内层 try/except 捕获): %s", exc)
