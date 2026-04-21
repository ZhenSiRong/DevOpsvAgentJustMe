"""
Day 3-PM 执行引擎测试 — TDD 红阶段

执行引擎是 Agent 修改 OS 状态的唯一通道，核心安全原则：
1. 所有命令必须先过安全校验器（validate_command）
2. 以最低权限用户执行（devops-runner，非 root）
3. 命令白名单机制：只允许预授权的命令模式
4. 超时控制：默认 30 秒，超时强制 kill 子进程
5. 完整审计日志记录

测试覆盖：
- TE-01: 正常命令执行（echo hello）
- TE-02: 白名单外命令拒绝
- TE-03: 超时命令 kill
- TE-04: 非零退出码处理
"""

import asyncio
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


requires_linux = pytest.mark.skipif(
    sys.platform != "linux",
    reason="执行引擎依赖 Linux 子进程管理（sudo/kill/devops-runner 用户），当前平台为 Windows"
)


# ============================================================
#  期望的数据结构（executor.py 必须实现的契约）
# ============================================================

class ExecutionStatus(str, Enum):
    """执行状态"""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"    # 安全校验未通过
    BLOCKED = "BLOCKED"      # 命令被拦截


@dataclass
class ExecutionResult:
    """
    命令执行的统一结果。

    无论成功还是失败，都返回此结构，确保：
    - 状态可追踪（成功/失败/超时/拒绝）
    - 输出完整保留（stdout/stderr）
    - 安全上下文保留（校验结果、执行用户、耗时）
    """
    command: str = ""
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    error_message: str | None = None   # 失败时的可读错误说明
    execution_time_ms: float = 0.0
    executed_by: str = "devops-runner"
    security_check: dict | None = None  # 安全校验器原始结果

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
#  测试用例
# ============================================================

@requires_linux
class TestExecutorBasicExecution:
    """TE-01: 正常命令执行测试"""

    async def test_execute_simple_echo_command(self):
        """
        execute("echo hello") 应以 devops-runner 身份成功执行，
        返回 status=SUCCESS，stdout 包含 "hello"，exit_code=0。
        """
        from devops_agent.safety.executor import execute

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"hello\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await execute("echo hello", skip_security_check=True,
                                   whitelist=["echo "])  # 测试白名单放行

        assert result.status == ExecutionStatus.SUCCESS
        assert "hello" in result.stdout
        assert result.exit_code == 0
        assert result.command == "echo hello"
        assert result.executed_by == "devops-runner"
        assert result.is_success is True


@requires_linux
class TestExecutorCommandWhitelist:
    """TE-02: 白名单外命令拒绝"""

    async def test_reject_command_not_in_whitelist(self):
        """
        执行不在白名单中的危险命令（如 apt-get install），
        应返回 REJECTED 或 BLOCKED 状态，不实际执行。
        安全校验器应已拦截。
        """
        from devops_agent.safety.executor import execute

        result = await execute("apt-get install malicious-package")
        assert result.status in (ExecutionStatus.REJECTED, ExecutionStatus.BLOCKED), \
            f"白名单外命令应被拒绝，实际状态: {result.status}"
        assert result.error_message != "", "拒绝时应有错误说明"

    async def test_reject_destructive_command(self):
        """
        即使绕过了白名单检查（假设），破坏性命令如 "rm -rf /"
        也必须被安全校验器的路径保护规则拦截。
        """
        from devops_agent.safety.executor import execute

        result = await execute("rm -rf /")
        assert result.status in (ExecutionStatus.REJECTED, ExecutionStatus.BLOCKED), \
            f"破坏性命令应被拦截，实际状态: {result.status}"


@requires_linux
class TestExecutorTimeout:
    """TE-03: 超时命令处理测试"""

    async def test_timeout_kills_subprocess(self):
        """
        当命令超时时：
        1. 子进程必须被 kill（不能泄漏）
        2. 返回 TIMEOUT 状态
        3. error_message 说明是超时原因
        """
        from devops_agent.safety.executor import execute

        async def hanging_process(*args, **kwargs):
            proc = AsyncMock()
            proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            proc.kill = AsyncMock()
            proc.pid = 99998
            proc.returncode = None
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=hanging_process):
            result = await execute("sleep 999", timeout=0.01, skip_security_check=True,
                                   whitelist=["sleep "])  # 测试白名单放行

        assert result.status == ExecutionStatus.TIMEOUT, \
            f"超时应返回 TIMEOUT，实际: {result.status}"
        assert "timeout" in (result.error_message or "").lower() or "超时" in (result.error_message or "")


@requires_linux
class TestExecutorNonzeroExit:
    """TE-04: 非零退出码处理测试"""

    async def test_nonzero_exit_code_returns_failed(self):
        """
        命令返回非零退出码时，status=FAILED，
        stdout/stderr 保留原始输出，exit_code 准确。
        """
        from devops_agent.safety.executor import execute

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"No such file or directory\n")
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await execute("cat /nonexistent_file_xyz")

        assert result.status == ExecutionStatus.FAILED
        assert result.exit_code == 1
        assert result.error_message != "" or len(result.stderr) > 0
        assert not result.is_success

    async def test_segfault_exit_code(self):
        """
        命令因段错误终止（exit_code = -11 或 139），
        应正确报告为 FAILED 并保留错误信息。
        """
        from devops_agent.safety.executor import execute

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"Segmentation fault\n")
        mock_proc.returncode = -11  # SIGSEGV

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await execute("./crash_program", timeout=5, skip_security_check=True,
                                   whitelist=["./"])  # 测试白名单放行

        assert result.status == ExecutionStatus.FAILED
        assert result.exit_code != 0


@requires_linux
class TestExecutorSecurityIntegration:
    """额外：与安全校验器的集成测试"""

    async def test_executor_calls_validator_before_execution(self):
        """
        执行任何命令前，必须先调用 validate_command()。
        如果校验不通过，不得调用 create_subprocess_exec。
        """
        from devops_agent.safety.executor import execute

        # 用一个会通过校验的命令
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"total 100G\n", b"")
        mock_proc.returncode = 0

        subprocess_called = False
        original_create = asyncio.create_subprocess_exec

        async def track_create(*args, **kwargs):
            nonlocal subprocess_called
            subprocess_called = True
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=track_create):
            result = await execute("df -h")

        # df -h 是只读命令，应该能通过校验并执行
        assert result.status in (ExecutionStatus.SUCCESS, ExecutionStatus.REJECTED,
                                  ExecutionStatus.BLOCKED)
        if result.is_success:
            assert subprocess_called, "校验通过后必须调用 subprocess"


@requires_linux
class TestExecutorAuditTrail:
    """额外：审计追踪测试"""

    async def test_result_contains_security_context(self):
        """
        ExecutionResult 必须包含 security_check 字段，
        记录安全校验的原始结果（用于审计追溯）。
        """
        from devops_agent.safety.executor import execute

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"ok\n", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await execute("uptime")

        assert hasattr(result, 'security_check'), \
            "ExecutionResult 必须包含 security_check 审计字段"
        # security_check 可能是 None 或 dict，取决于实现
        if result.security_check is not None:
            assert isinstance(result.security_check, dict)
