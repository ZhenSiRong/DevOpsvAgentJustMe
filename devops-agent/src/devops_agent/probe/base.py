"""
探针基类与公共数据类型。

所有探针共享的契约：
- 统一返回 ProbeResult 包装
- 超时控制（默认 30s）
- 异步执行
- 错误不抛出，封装在 ProbeResult.error 中
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class ProbeStatus(str, Enum):
    """探针执行状态"""
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass
class DiskUsageResult:
    """磁盘使用率结果"""
    filesystem: str = ""
    total: int = 0
    used: int = 0
    available: int = 0
    usage_percent: float = 0.0
    mount_point: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LargeFileResult:
    """大文件扫描结果"""
    path: str = ""
    size_bytes: int = 0
    modified: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProcessInfo:
    """进程信息"""
    pid: int = 0
    user: str | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    command: str = ""
    state: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NetworkConnection:
    """网络连接信息"""
    protocol: str = ""
    local_addr: str = ""
    local_port: int = 0
    remote_addr: str | None = None
    remote_port: int | None = None
    state: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str = ""
    source: str | None = None
    message: str = ""
    priority: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProbeResult:
    """
    探针统一返回包装。

    所有探针函数都应返回此包装，确保状态可追踪、数据类型一致。
    """
    status: ProbeStatus = ProbeStatus.SUCCESS
    data: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0
    probe_name: str = ""
    captured_at: str = ""

    @property
    def is_success(self) -> bool:
        return self.status == ProbeStatus.SUCCESS

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_success"] = self.is_success
        return d


class ProbeTimeoutError(Exception):
    """探针执行超时异常"""
    pass


# ============================================================
#  探针执行引擎（公共基础设施）
# ============================================================

async def _run_command(
    *args: str,
    timeout: float = 30.0,
    parse_func=None,
) -> tuple[str | None, int, str]:
    """
    异步执行命令并获取输出。

    Returns:
        (stdout_text, returncode, error_msg) 三元组。
        成功时 error_msg 为空字符串。
    """
    start_time = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            # 超时：强制杀掉子进程
            try:
                proc.kill()
                await proc.wait()
            except (ProcessLookupError, OSError):
                pass

            elapsed = (time.monotonic() - start_time) * 1000
            return (
                None,
                -1,
                f"命令执行超时（{timeout}s），已终止子进程",
            )

        elapsed = (time.monotonic() - start_time) * 1000
        stdout_text = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""

        if proc.returncode != 0:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
            return (None, proc.returncode, f"命令返回非零退出码 {proc.returncode}: {stderr_text[:200]}")

        return (stdout_text, 0, "")

    except FileNotFoundError:
        elapsed = (time.monotonic() - start_time) * 1000
        return (None, -1, f"命令不存在: {args[0]}")
    except Exception as e:
        elapsed = (time.monotonic() - start_time) * 1000
        return (None, -1, f"执行异常: {type(e).__name__}: {str(e)}")


def _make_result(
    probe_name: str,
    status: ProbeStatus,
    data: Any = None,
    error: str | None = None,
    execution_time_ms: float = 0.0,
) -> ProbeResult:
    from datetime import datetime, timezone
    return ProbeResult(
        status=status,
        data=data,
        error=error,
        execution_time_ms=round(execution_time_ms, 2),
        probe_name=probe_name,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )


__all__ = [
    "ProbeStatus",
    "DiskUsageResult",
    "LargeFileResult",
    "ProcessInfo",
    "NetworkConnection",
    "LogEntry",
    "ProbeResult",
    "ProbeTimeoutError",
    "_run_command",
    "_make_result",
]
