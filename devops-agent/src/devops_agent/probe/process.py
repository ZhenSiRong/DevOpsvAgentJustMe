"""
进程探针模块 — 感知系统运行中的进程。

提供的接口：
- process_list(filter_str)  → 匹配指定过滤字符串的进程列表
- process_detail(pid)       → 单个进程的详细信息
"""

from __future__ import annotations

import re

from .base import (
    ProcessInfo,
    ProbeResult,
    ProbeStatus,
    _run_command,
    _make_result,
)


async def process_list(filter_str: str = "", timeout: float = 30.0) -> ProbeResult:
    """
    获取匹配过滤条件的进程列表。

    使用 `ps aux` 获取所有进程信息，然后在 Python 层做过滤
    （避免 shell 注入风险，不使用 `ps aux | grep xxx`）。

    Args:
        filter_str: 进程命令行或用户名过滤字符串（大小写敏感）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - pid: 进程号 (int)
        - user: 运行用户
        - cpu_percent / memory_percent: CPU 和内存占用率
        - command: 完整命令行
        - state: 进程状态 (R/S/D/Z/T)
        如果 filter_str 非空，只返回 command 中包含该字符串的进程。
    """
    probe_name = "process_list"

    # ps aux 输出：USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
    stdout, rc, err = await _run_command(
        "ps", "aux", "--no-headers",
        timeout=timeout,
    )

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    if stdout is None:
        if "超时" in err or "timeout" in err.lower():
            return _make_result(probe_name, ProbeStatus.TIMEOUT, error=err)
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    processes = []
    lines = stdout.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # ps aux --no-headers 格式：
        # USER  PID  %CPU %MEM   VSZ   RSS TTY STAT START TIME COMMAND
        parts = line.split(None, 10)  # maxsplit=10，保留完整 COMMAND
        if len(parts) < 11:
            continue

        pid = _safe_int(parts[1])
        cmd = parts[10]

        # 过滤：如果提供了 filter_str，只保留匹配的进程
        if filter_str and filter_str.lower() not in cmd.lower():
            continue

        processes.append(ProcessInfo(
            pid=pid,
            user=parts[0],
            cpu_percent=_safe_float(parts[2]),
            memory_percent=_safe_float(parts[3]),
            command=cmd,
            state=_extract_state(parts[7]) if len(parts) > 7 else None,
        ).to_dict())

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=processes,
    )


async def process_detail(pid: int, timeout: float = 10.0) -> ProbeResult:
    """
    获取单个进程的详细信息。

    使用 `ps -p <pid> -o pid,user,%cpu,%mem,state,command --no-headers`

    Args:
        pid: 目标进程 PID
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 dict 或 None（进程不存在）
    """
    probe_name = "process_detail"

    stdout, rc, err = await _run_command(
        "ps", "-p", str(pid),
        "-o", "pid,user,%cpu,%mem,state,comm",
        "--no-headers",
        timeout=timeout,
    )

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.SUCCESS, data=None)

    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    line = stdout.strip()
    if not line:
        return _make_result(probe_name, ProbeStatus.SUCCESS, data=None)

    parts = line.split(None, 5)
    if len(parts) < 6:
        return _make_result(probe_name, ProbeStatus.SUCCESS, data=None)

    detail = ProcessInfo(
        pid=_safe_int(parts[0]),
        user=parts[1],
        cpu_percent=_safe_float(parts[2]),
        memory_percent=_safe_float(parts[3]),
        state=parts[4],
        command=parts[5] if len(parts) > 5 else "",
    )

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=detail.to_dict(),
    )


def _extract_state(stat_field: str) -> str | None:
    """
    从 STAT 字段中提取主进程状态字符。

    STAT 字段可能包含多线程标志（如 'Sl' 表示 sleep + 多线程），
    我们取第一个字母作为主要状态。
    """
    if not stat_field:
        return None
    first_char = stat_field[0]
    valid_states = {"R", "S", "D", "Z", "T", "t", "X", "x", "K", "W", "I", "P"}
    return first_char if first_char in valid_states else None


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _safe_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


__all__ = [
    "process_list",
    "process_detail",
]
