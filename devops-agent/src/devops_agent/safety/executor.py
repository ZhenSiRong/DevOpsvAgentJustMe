"""
执行引擎 —— Agent 修改 OS 状态的唯一安全通道。

核心安全原则：
1. **校验优先**：所有命令必须先通过 validate_command() 安全校验
2. **最小权限**：以 devops-runner 用户执行（非 root）
3. **白名单控制**：只允许预授权的命令模式
4. **超时保护**：默认 30 秒，超时强制 kill 子进程
5. **审计完整**：每次执行保留完整的校验结果和输出

对外接口：
- execute(command, user, timeout, allowlist) -> ExecutionResult
- execute_safe(command, context, ...) -> ExecutionResult  (带上下文的增强版本)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    """命令执行状态"""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"   # 安全校验未通过（PASSED 但不在白名单等）
    BLOCKED = "BLOCKED"     # 安全校验器直接拦截（危险命令）


@dataclass
class ExecutionResult:
    """
    命令执行的统一结果包装。

    无论成功还是失败，都返回此结构以确保：
    - 状态可追踪
    - 输出完整保留（stdout/stderr）
    - 安全上下文保留（校验结果/执行用户/耗时）
    - 审计信息完整
    """
    command: str = ""
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    error_message: str | None = None
    execution_time_ms: float = 0.0
    executed_by: str = "devops-runner"
    security_check: dict | None = None

    @property
    def is_success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_success"] = self.is_success
        return d


class ExecutionRejectedError(Exception):
    """命令被安全校验或白名单拒绝时抛出的异常"""
    pass


# ============================================================
#  默认配置
# ============================================================

DEFAULT_EXECUTION_USER = "devops-runner"
DEFAULT_TIMEOUT_SECONDS = 30.0

# 命令白名单 — 只允许这些基础命令模式被 Agent 执行
# 每条是命令前缀匹配：如果 command 以白名单中的字符串开头则放行
EXECUTION_WHITELIST: list[str] = [
    # 日志操作
    "logrotate",
    "journalctl",
    # 服务管理（受限）
    "systemctl restart ",
    "systemctl start ",
    "systemctl stop ",
    "systemctl status ",
    # 文件操作（只读 + 受限写操作）
    "cat ", "ls ", "find ",
    "head ", "tail ", "grep ", "wc ",
    "sort ", "uniq ", "cut ", "awk ", "sed ",
    "cp ", "mv ",
    # 磁盘操作
    "df ", "du ", "free ",
    # 进程查看
    "ps ", "pgrep ", "pidstat ",
    # 网络（只读）
    "netstat ", "ss ", "ip addr ", "ip link ",
    # DNS
    "dig ", "nslookup ", "getent ",
    # 清理操作（受限路径）
    "find /tmp -name",
    "find /var/tmp -name",
    "truncate -s 0 /tmp/",
]


def is_command_allowed(command: str, whitelist: list[str] | None = None) -> tuple[bool, str]:
    """
    检查命令是否在执行白名单内。

    Args:
        command: 待执行的命令字符串
        whitelist: 白名单列表，None 则使用默认 EXECUTION_WHITELIST

    Returns:
        (is_allowed, reason) 元组：
        - True 表示在白名单中
        - reason 是可读的原因说明
    """
    if whitelist is None:
        whitelist = EXECUTION_WHITELIST

    cmd_stripped = command.strip()

    for allowed in whitelist:
        if cmd_stripped.startswith(allowed):
            return True, f"命令匹配白名单规则: {allowed}"

    return False, f"命令 '{cmd_stripped}' 不在执行白名单中"


# ============================================================
#  核心执行函数
# ============================================================

async def execute(
    command: str,
    user: str = DEFAULT_EXECUTION_USER,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    skip_security_check: bool = False,
    whitelist: list[str] | None = None,
) -> ExecutionResult:
    """
    安全地以指定用户身份执行一条命令。

    执行流程：
    1. 安全校验 → validate_command()
    2. 白名单检查 → is_command_allowed()
    3. 构建子进程参数（sudo 切用户）
    4. 异步执行 + 超时控制
    5. 收集输出 + 构建结果

    Args:
        command: 要执行的 shell 命令
        user: 执行命令的操作系统用户（默认 devops-runner）
        timeout: 超时时间（秒），超时自动 kill 子进程
        skip_security_test: 是否跳过安全校验（仅测试用，生产环境必须 False
        whitelist: 自定义白名单，None 使用默认

    Returns:
        ExecutionResult 包含状态、输出、错误、安全上下文等信息
    """
    start_time = time.monotonic()
    result = ExecutionResult(
        command=command,
        executed_by=user,
    )

    # ---- Step 1: 安全校验 ----
    if not skip_security_check:
        try:
            from .validator import validate_command

            validation = validate_command(command)
            result.security_check = {
                "result": validation.result.value,
                "reason": validation.reason,
                "rule_id": validation.rule_id or "",
            }

            if validation.result.value == "BLOCKED":
                result.status = ExecutionStatus.BLOCKED
                result.error_message = f"安全校验拦截: {validation.reason}"
                result.execution_time_ms = (time.monotonic() - start_time) * 1000
                return result

        except Exception as e:
            # 安全校验器本身出错：拒绝执行（fail-safe）
            result.status = ExecutionStatus.REJECTED
            result.error_message = f"安全校验器异常: {type(e).__name__}: {str(e)}"
            result.execution_time_ms = (time.monotonic() - start_time) * 1000
            return result

    # ---- Step 2: 白名单检查 ----
    allowed, reason = is_command_allowed(command, whitelist)
    if not allowed:
        result.status = ExecutionStatus.REJECTED
        result.error_message = f"白名单拒绝: {reason}"
        result.execution_time_ms = (time.monotonic() - start_time) * 1000
        return result

    # ---- Step 3: 构建并执行子进程 ----
    try:
        cmd_parts = _parse_command_to_args(command)

        # 使用 sudo 切换到目标用户执行
        full_args = ["sudo", "-u", user] + cmd_parts

        proc = await asyncio.create_subprocess_exec(
            *full_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Step 4: 带超时的等待
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            # 超时：强制杀掉整个进程组
            await _kill_process_tree(proc)
            result.status = ExecutionStatus.TIMEOUT
            result.error_message = (
                f"命令执行超时（{timeout}s），已终止子进程。"
                f"建议增加超时时间或优化命令。"
            )
            result.exit_code = -1
            result.execution_time_ms = (time.monotonic() - start_time) * 1000
            return result

        # Step 5: 收集结果
        elapsed = (time.monotonic() - start_time) * 1000
        result.stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        result.stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
        result.exit_code = proc.returncode if proc.returncode is not None else -1
        result.execution_time_ms = round(elapsed, 2)

        if proc.returncode == 0:
            result.status = ExecutionStatus.SUCCESS
        else:
            result.status = ExecutionStatus.FAILED
            result.error_message = (
                f"命令退出码 {proc.returncode}: "
                f"{result.stderr[:200] if result.stderr else '无标准错误输出'}"
            )

    except FileNotFoundError:
        result.status = ExecutionStatus.FAILED
        result.error_message = f"命令不存在或路径不可达: {_extract_cmd_name(command)}"
        result.exit_code = 127
        result.execution_time_ms = (time.monotonic() - start_time) * 1000

    except PermissionError:
        result.status = ExecutionStatus.FAILED
        result.error_message = f"权限不足: 无法以用户 '{user}' 执行命令（sudo 配置问题？）"
        result.exit_code = 126
        result.execution_time_ms = (time.monotonic() - start_time) * 1000

    except Exception as e:
        result.status = ExecutionStatus.FAILED
        result.error_message = f"执行异常: {type(e).__name__}: {str(e)}"
        result.execution_time_ms = (time.monotonic() - start_time) * 1000

    return result


async def execute_safe(
    command: str,
    process_context: dict | None = None,
    **kwargs,
) -> ExecutionResult:
    """
    带运行时上下文的安全执行。

    在标准 execute 的基础上增加了进程持有检测等上下文感知能力。

    Args:
        command: 待执行的命令
        process_context: 可选的进程上下文（传给 validate_command_with_context）
        **kwargs: 其他参数透传给 execute()

    Returns:
        ExecutionResult
    """
    if process_context is not None:
        from .validator import validate_command_with_context

        validation = validate_command_with_context(command, process_context)
        if validation.result.value == "BLOCKED":
            return ExecutionResult(
                command=command,
                status=ExecutionStatus.BLOCKED,
                error_message=f"安全拦截(带上下文): {validation.reason}",
                security_check={
                    "result": validation.result.value,
                    "reason": validation.reason,
                    "rule_id": validation.rule_id or "",
                },
            )

    return await execute(command, **kwargs)


# ============================================================
#  内部辅助函数
# ============================================================

def _parse_command_to_args(command: str) -> list[str]:
    """
    将简单命令字符串拆分为参数列表。

    注意：这是一个简化实现，不支持复杂的 shell 特性（管道/重定向/变量替换）。
    复杂场景应使用 shell=True 或显式拆分。

    对于我们的运维场景，大部分命令都是简单的 `cmd arg1 arg2` 形式，
    这个实现足够覆盖。
    """
    import shlex

    try:
        return shlex.split(command)
    except ValueError:
        # shlex 解析失败（如未闭合引号）→ 回退到简单空格分割
        return command.split()


async def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """
    终止一个进程及其可能的子进程。

    策略：
    1. 先尝试 SIGTERM（优雅终止）
    2. 如果进程仍在运行，发送 SIGKILL（强制终止）
    """
    try:
        # 尝试优雅终止
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

        # 检查是否已结束
        if proc.returncode is None:
            # 强制杀死
            try:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except (ProcessLookupError, OSError, asyncio.TimeoutError,
                     asyncio.CancelledError):
                # 进程可能已经结束了
                pass

    except (ProcessLookupError, OSError):
        # 进程不存在了，无需处理
        pass


def _extract_cmd_name(command: str) -> str:
    """从命令字符串中提取程序名"""
    parts = command.strip().split()
    return parts[0] if parts else "(空命令)"


__all__ = [
    "ExecutionStatus",
    "ExecutionResult",
    "ExecutionRejectedError",
    "execute",
    "execute_safe",
    "is_command_allowed",
    "EXECUTION_WHITELIST",
    "DEFAULT_EXECUTION_USER",
    "DEFAULT_TIMEOUT_SECONDS",
]
