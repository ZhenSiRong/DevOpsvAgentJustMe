"""
安全校验器 —— 赛题核心功能

三层校验流程：
1. 只读白名单快速放行 → PASSED
2. 路径保护 + 危险模式正则匹配 → BLOCKED
3. 权限提升检测 → ESCALATE / BLOCKED（取决于是否在白名单）
4. 默认 → PASSED（允许执行的正常运维操作）

对外接口：
- validate_command(command) -> ValidationResult        # 单条命令校验
- validate_command_with_context(command, context) ->     # 带进程上下文校验
- validate_batch_commands(commands) -> BatchValidationResult  # 批量校验
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .rules import (
    DANGER_PATTERNS,
    DEFAULT_SUDO_ALLOWLIST,
    PROTECTED_PATHS,
    READONLY_WHITELIST_PATTERNS,
    SENSITIVE_FILES,
    is_readonly_command,
    matches_sudo_allowlist,
    needs_privilege_escalation,
)


# ============================================================
#  公共数据类型（与 test_safety_validator.py 中的定义一致）
# ============================================================

class SecurityResult(Enum):
    """安全校验结果枚举"""
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"
    ESCALATE = "ESCALATE"


@dataclass
class ValidationResult:
    """单条命令的校验结果"""
    command: str
    result: SecurityResult
    reason: str = ""
    rule_id: str = ""
    suggestion: str = ""


@dataclass
class BatchValidationResult:
    """批量操作的校验结果集合"""
    results: list[ValidationResult]
    passed_count: int = 0
    blocked_count: int = 0
    warning_count: int = 0
    is_all_passed: bool = True

    def __post_init__(self) -> None:
        self.passed_count = sum(1 for r in self.results if r.result == SecurityResult.PASSED)
        self.blocked_count = sum(1 for r in self.results if r.result == SecurityResult.BLOCKED)
        self.warning_count = sum(1 for r in self.results if r.result == SecurityResult.WARNING)
        self.is_all_passed = self.blocked_count == 0


# ============================================================
#  核心校验逻辑 —— 三层过滤流水线
# ============================================================

def validate_command(command: str) -> ValidationResult:
    """
    对单条命令执行完整的三层安全校验。
    
    流水线：
    Layer 1: 空命令检查
    Layer 2: 只读白名单快速通道
    Layer 3: 路径保护规则（CRITICAL 级别直接 BLOCKED）
    Layer 4: 敏感文件保护规则
    Layer 5: 危险模式正则匹配
    Layer 6: 权限提升检查（sudo / 白名单）
    Layer 7: 默认放行
    """
    
    cmd_stripped = command.strip()
    
    # ---- Layer 1: 空命令 ----
    if not cmd_stripped:
        return ValidationResult(
            command=command,
            result=SecurityResult.PASSED,
            reason="空命令，无需校验",
        )
    
    # ---- Layer 2: 只读命令白名单快速放行 ----
    if _is_safe_readonly(cmd_stripped):
        return ValidationResult(
            command=command,
            result=SecurityResult.PASSED,
            reason="只读探针命令，不修改系统状态",
        )
    
    # ---- Layer 3: 路径保护规则（CRITICAL） ----
    path_result = _check_protected_paths(cmd_stripped)
    if path_result:
        return path_result
    
    # ---- Layer 4: 敏感文件保护规则 ----
    file_result = _check_sensitive_files(cmd_stripped)
    if file_result:
        return file_result
    
    # ---- Layer 5: 危险模式正则匹配 ----
    danger_result = _check_danger_patterns(cmd_stripped)
    if danger_result:
        return danger_result
    
    # ---- Layer 6: 权限提升检测 ----
    escalation_result = _check_privilege_escalation(cmd_stripped)
    if escalation_result:
        return escalation_result
    
    # ---- Layer 7: 默认放行 ----
    return ValidationResult(
        command=command,
        result=SecurityResult.PASSED,
        reason="命令通过所有安全校验规则",
    )


def validate_command_with_context(
    command: str,
    process_context: dict | None = None,
) -> ValidationResult:
    """
    带运行时上下文的安全校验。
    
    额外能力：
    - 检测目标文件是否被活跃进程持有 (WARNING)
    - 结合当前系统负载判断风险
    
    Args:
        command: 待校验的命令
        process_context: 可选的进程上下文信息
            - held_by: 持有文件名的进程名
            - pid: 进程 PID
            - file_path: 目标文件路径
    """
    # 先走标准校验流程
    base_result = validate_command(command)
    
    # 如果已经被 BLOCKED 了，不需要额外上下文分析
    if base_result.result == SecurityResult.BLOCKED:
        return base_result
    
    # 进程持有检测：如果命令涉及被进程持有的文件，升级为 WARNING
    if process_context and "held_by" in process_context:
        held_by = process_context["held_by"]
        pid = process_context.get("pid", "unknown")
        
        return ValidationResult(
            command=command,
            result=SecurityResult.WARNING,
            reason=(
                f"目标文件正被进程 '{held_by}'(PID:{pid}) 持有。"
                f"强制操作可能导致该进程异常或数据丢失。建议先停止相关服务。"
            ),
            rule_id="CTX-001",
            suggestion=f"先执行 'systemctl stop {held_by}' 或确认进程状态后再操作",
        )
    
    return base_result


def validate_batch_commands(commands: list[str]) -> BatchValidationResult:
    """
    对多条命令批量校验。
    
    逐条调用 validate_command，汇总结果。
    只要有一条 BLOCKED，is_all_passed=False。
    """
    results = [validate_command(cmd) for cmd in commands]
    return BatchValidationResult(results=results)


# ============================================================
#  内部实现 —— 各层的具体检查逻辑
# ============================================================

def _is_safe_readonly(command: str) -> bool:
    """
    判断是否为只读/安全命令。
    
    放行条件：
    - 匹配只读白名单正则
    - 特殊情况：find 带 -delete 参数不算只读！
    - 特殊情况：管道后接 rm 的不算只读
    """
    if not is_readonly_command(command):
        return False
    
    # 二次确认：排除表面像只读但实际有破坏性的变体
    dangerous_readonly_variants = [
        r".*-delete",           # find ... -delete
        r"\|\s*rm\b",          # ... | rm ...
        r">\s*/(?:etc|boot)",  # 重定向写入敏感目录
        r"mv\s+.*?/(?:etc|boot|usr/bin)/",  # 移动到系统目录
    ]
    
    for pattern in dangerous_readonly_variants:
        if re.search(pattern, command):
            return False
    
    return True


def _check_protected_paths(command: str) -> ValidationResult | None:
    """Layer 3: 检查是否命中受保护的路径规则"""
    for rule in PROTECTED_PATHS:
        if re.search(rule["pattern"], command):
            reason = rule["reason_template"].format(
                cmd=command[:80],
                path=_extract_path_from_command(command),
            )
            return ValidationResult(
                command=command,
                result=SecurityResult.BLOCKED,
                reason=reason,
                rule_id=rule["rule_id"],
            )
    return None


def _check_sensitive_files(command: str) -> ValidationResult | None:
    """Layer 4: 检查是否涉及敏感配置文件的修改/删除"""
    for rule in SENSITIVE_FILES:
        for pattern in rule["patterns"]:
            if re.search(pattern, command):
                return ValidationResult(
                    command=command,
                    result=SecurityResult.BLOCKED,
                    reason=rule["reason_template"],
                    rule_id=rule["rule_id"],
                )
    return None


def _check_danger_patterns(command: str) -> ValidationResult | None:
    """Layer 5: 正则匹配已知的危险命令模式"""
    for rule in DANGER_PATTERNS:
        if re.search(rule["pattern"], command):
            return ValidationResult(
                command=command,
                result=SecurityResult.BLOCKED,
                reason=rule["reason_template"],
                rule_id=rule["rule_id"],
            )
    return None


def _check_privilege_escalation(command: str) -> ValidationResult | None:
    """
    Layer 6: 检测权限提升需求。
    
    逻辑：
    - 如果需要 sudo 且在白名单内 → ESCALATE（表示可以提权但需记录）
    - 如果需要 sudo 但不在白名单内 → BLOCKED
    """
    if needs_privilege_escalation(command):
        if matches_sudo_allowlist(command):
            return ValidationResult(
                command=command,
                result=SecurityResult.ESCALATE,
                reason=f"命令需要提权执行，但在 sudo 白名单范围内",
                rule_id="PRIV-001",
            )
        else:
            return ValidationResult(
                command=command,
                result=SecurityResult.BLOCKED,
                reason="需要提权的命令不在 sudo 白名单中，拒绝执行",
                rule_id="PRIV-002",
                suggestion="如确需执行此操作，请手动通过终端以 root 身份完成",
            )
    return None


def _extract_path_from_command(command: str) -> str:
    """从命令中提取可能涉及的文件路径（用于错误消息展示）"""
    # 简单启发式：提取以 / 开头的路径片段
    paths = re.findall(r'/[\w./\-]+', command)
    return paths[0] if paths else "(未知路径)"


__all__ = [
    "SecurityResult",
    "ValidationResult",
    "BatchValidationResult",
    "validate_command",
    "validate_command_with_context",
    "validate_batch_commands",
]
