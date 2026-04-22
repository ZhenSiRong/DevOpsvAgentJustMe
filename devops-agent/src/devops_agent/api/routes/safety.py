"""
安全层 API 路由 —— Phase 2 核心安全能力暴露

端点列表:
- POST /api/v1/safety/validate         单条命令安全校验
- POST /api/v1/safety/validate/batch   批量命令安全校验
- POST /api/v1/safety/execute          安全执行命令（校验+执行）
- POST /api/v1/safety/config/baseline  采集配置基线快照
- POST /api/v1/safety/config/scan      全量扫描配置变更
- POST /api/v1/safety/config/check-write  写操作预检
- POST /api/v1/safety/injection/scan   提示词注入检测
- GET  /api/v1/safety/injection/stats  防护盾运行统计
- GET  /api/v1/safety/status           安全层总览
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..schemas import APIResponse
from ...safety import (
    # Validator
    validate_command,
    validate_batch_commands,
    SecurityResult,
    # Executor
    execute_safe,
    ExecutionResult,
    ExecutionStatus,
    is_command_allowed,
    # Config Guard
    ConfigGuard,
    ConfigProtectionLevel,
    # Prompt Injection
    PromptInjectionShield,
    scan_input,
    get_shield,
)

router = APIRouter(prefix="/api/v1/safety", tags=["Safety — 核心安全层"])

# ============================================================
#  Pydantic 请求模型
# ============================================================

class ValidateCommandRequest(BaseModel):
    command: str = Field(..., description="待校验的命令字符串")
    context: dict | None = Field(None, description="可选的运行时上下文")


class ValidateBatchRequest(BaseModel):
    commands: list[str] = Field(..., description="待校验的命令列表")


class ExecuteCommandRequest(BaseModel):
    command: str = Field(..., description="待执行的命令字符串")
    user: str = Field("devops-runner", description="执行用户（默认 devops-runner）")
    timeout: float = Field(30.0, description="超时时间（秒）")
    skip_security: bool = Field(False, description="仅测试用：跳过安全校验")


class ConfigBaselineRequest(BaseModel):
    paths: list[str] | None = Field(None, description="指定路径，None 使用默认保护清单")


class ConfigScanRequest(BaseModel):
    quick: bool = Field(True, description="True 只检查已建立基线的文件")


class ConfigWriteCheckRequest(BaseModel):
    path: str = Field(..., description="待写入的目标路径")


class InjectionScanRequest(BaseModel):
    text: str = Field(..., description="待扫描的输入文本")
    apply_isolation: bool = Field(True, description="是否应用结构化隔离")


# ============================================================
#  全局单例
# ============================================================

_config_guard_instance: ConfigGuard | None = None


def _get_config_guard() -> ConfigGuard:
    global _config_guard_instance
    if _config_guard_instance is None:
        _config_guard_instance = ConfigGuard()
    return _config_guard_instance


# ============================================================
#  1. 命令安全校验
# ============================================================

@router.post("/validate", response_model=APIResponse, summary="单条命令安全校验")
async def api_validate_command(req: ValidateCommandRequest) -> APIResponse:
    """
    对单条命令执行七层安全校验流水线。

    返回结果包含：
    - result: PASSED / BLOCKED / WARNING / ESCALATE
    - reason: 人类可读的原因
    - rule_id: 命中的规则编号
    """
    if req.context:
        from ...safety import validate_command_with_context
        result = validate_command_with_context(req.command, req.context)
    else:
        result = validate_command(req.command)

    return APIResponse(data={
        "command": result.command,
        "result": result.result.value,
        "reason": result.reason,
        "rule_id": result.rule_id,
        "suggestion": result.suggestion,
    })


@router.post("/validate/batch", response_model=APIResponse, summary="批量命令安全校验")
async def api_validate_batch(req: ValidateBatchRequest) -> APIResponse:
    """对多条命令批量执行安全校验。"""
    batch_result = validate_batch_commands(req.commands)

    return APIResponse(data={
        "results": [
            {
                "command": r.command,
                "result": r.result.value,
                "reason": r.reason,
                "rule_id": r.rule_id,
            }
            for r in batch_result.results
        ],
        "summary": {
            "total": len(batch_result.results),
            "passed": batch_result.passed_count,
            "blocked": batch_result.blocked_count,
            "warning": batch_result.warning_count,
            "is_all_passed": batch_result.is_all_passed,
        },
    })


# ============================================================
#  2. 安全命令执行（仅允许白名单命令真正执行）
# ============================================================

@router.post("/execute", response_model=APIResponse, summary="安全执行命令")
async def api_execute_command(req: ExecuteCommandRequest) -> APIResponse:
    """
    以安全方式执行一条命令。

    执行流程：
    1. 安全校验（validate_command）
    2. 白名单检查
    3. sudo 切换到指定用户执行
    4. 超时保护

    ⚠️ 生产环境必须确保 skip_security=False
    """
    if not req.command.strip():
        raise HTTPException(status_code=422, detail="命令不能为空")

    result = await execute_safe(
        command=req.command,
        user=req.user,
        timeout=req.timeout,
        skip_security_check=req.skip_security,
    )

    return APIResponse(data={
        "command": result.command,
        "status": result.status.value,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error_message": result.error_message,
        "execution_time_ms": result.execution_time_ms,
        "executed_by": result.executed_by,
        "security_check": result.security_check,
    })


# ============================================================
#  3. 配置写保护
# ============================================================

@router.post("/config/baseline", response_model=APIResponse, summary="采集配置基线快照")
async def api_config_baseline(req: ConfigBaselineRequest | None = None) -> APIResponse:
    """
    对所有受保护的配置文件建立基线快照。

    基线内容包括：SHA256、权限、属主、大小、修改时间。
    小文件（<64KB）还会保存完整内容快照。
    """
    guard = _get_config_guard()
    paths = req.paths if req and req.paths else None

    if paths:
        # 使用用户自定义路径列表
        guard_custom = ConfigGuard(protected_files=[
            {"path": p, "protection_level": ConfigProtectionLevel.MONITORED}
            for p in paths
        ])
        stats = await guard_custom.initialize()
        return APIResponse(data={
            "stats": stats,
            "baseline_count": len(guard_custom.baselines),
            "baselines": [bl.to_dict() for bl in guard_custom.baselines.values()],
        })

    # 使用默认保护清单
    stats = await guard.initialize()
    return APIResponse(data={
        "stats": stats,
        "baseline_count": len(guard.baselines),
        "guard_stats": guard.get_baseline_stats(),
    })


@router.post("/config/scan", response_model=APIResponse, summary="全量扫描配置变更")
async def api_config_scan(req: ConfigScanRequest | None = None) -> APIResponse:
    """
    对比当前文件状态与基线快照，检测未授权变更。

    返回每个受保护文件的变更状态。
    """
    guard = _get_config_guard()
    if not guard.is_initialized:
        return APIResponse(
            code=400,
            message="基线尚未建立，请先调用 /config/baseline",
            data={},
        )

    reports = await guard.scan_all()
    summary = guard.get_scan_summary(reports)

    return APIResponse(data={
        "summary": summary,
        "reports": [r.to_dict() for r in reports if r.has_change],
    })


@router.post("/config/check-write", response_model=APIResponse, summary="写操作预检")
async def api_config_check_write(req: ConfigWriteCheckRequest) -> APIResponse:
    """
    在 Agent 执行任何写操作前，预检查目标路径是否受保护。

    返回：
    - allowed: 是否允许写入
    - level: 保护级别（READONLY / MONITORED / RESTRICTED / UNPROTECTED）
    - reason: 决策说明
    """
    guard = _get_config_guard()
    result = guard.check_write_allowed(req.path)

    return APIResponse(data={
        "allowed": result.allowed,
        "path": result.path,
        "reason": result.reason,
        "protection_level": result.protection_level,
        "rule_id": result.rule_id,
    })


@router.get("/config/paths", response_model=APIResponse, summary="列出所有受保护路径")
async def api_config_paths() -> APIResponse:
    """获取所有受保护路径及其状态的概览。"""
    guard = _get_config_guard()
    return APIResponse(data={
        "protected_paths": guard.get_protected_paths_list(),
        "baseline_stats": guard.get_baseline_stats(),
    })


# ============================================================
#  4. 提示词注入防护
# ============================================================

@router.post("/injection/scan", response_model=APIResponse, summary="提示词注入检测")
async def api_injection_scan(req: InjectionScanRequest) -> APIResponse:
    """
    对用户输入执行三层注入检测（正则 + 结构化隔离 + 语义审计）。

    返回检测结果、匹配的攻击模式、风险评级和建议。
    """
    result = scan_input(req.text)

    return APIResponse(data={
        "is_blocked": result.is_blocked,
        "highest_severity": result.highest_severity.value,
        "match_count": result.match_count,
        "matches": [
            {
                "pattern_id": m.pattern_id,
                "pattern_name": m.pattern_name,
                "type": m.pattern_type.value,
                "severity": m.severity.value,
                "matched_text": m.matched_text,
                "position": m.position,
            }
            for m in result.matches
        ],
        "recommendations": result.recommendations,
        "input_hash": result.input_hash,
        "isolation_applied": result.isolation_applied,
        "scan_timestamp": result.scan_timestamp,
    })


@router.get("/injection/stats", response_model=APIResponse, summary="防护盾运行统计")
async def api_injection_stats() -> APIResponse:
    """获取提示词注入防护盾的运行统计数据。"""
    shield = get_shield()
    return APIResponse(data={
        "stats": shield.get_stats(),
        "rules": shield.get_rules_summary(),
    })


# ============================================================
#  5. 安全层总览
# ============================================================

@router.get("/status", response_model=APIResponse, summary="安全层总览状态")
async def api_safety_status() -> APIResponse:
    """
    获取安全层各模块的运行状态和统计。
    """
    shield = get_shield()
    guard = _get_config_guard()

    # 白名单命令数
    from ...safety import EXECUTION_WHITELIST, DEFAULT_SUDO_ALLOWLIST

    return APIResponse(data={
        "security_modules": {
            "validator": {
                "status": "active",
                "rules_loaded": "路径保护(5) + 敏感文件(3) + 危险模式(5) + 只读白名单",
                "layers": 7,
            },
            "executor": {
                "status": "active",
                "default_user": "devops-runner",
                "default_timeout_sec": 30,
                "whitelist_count": len(EXECUTION_WHITELIST),
            },
            "config_guard": {
                "status": "ready" if guard.is_initialized else "not_initialized",
                "protected_paths": len(guard.protected_files),
                "baseline_captured": len(guard.baselines),
            },
            "prompt_injection_shield": {
                "status": "active",
                "rules_loaded": shield.get_stats()["rules_loaded"],
                "total_scans": shield.get_stats()["total_scans"],
                "total_blocks": shield.get_stats()["total_blocks"],
            },
        },
        "sudo_allowlist_count": len(DEFAULT_SUDO_ALLOWLIST),
    })
