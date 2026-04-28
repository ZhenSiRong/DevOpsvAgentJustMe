"""
系统监控探针模块 — CPU、内存、负载、整体状态。

提供的接口：
- system_top(limit)       → CPU/内存占用最高的 N 个进程
- memory_usage()          → 内存用量统计
- system_uptime()         → 系统负载与运行时长
- system_vmstat(count)    → 系统整体状态采样
"""

from __future__ import annotations

import re
from typing import Any

from .base import (
    ProbeResult,
    ProbeStatus,
    _run_command,
    _make_result,
)


async def system_top(limit: int = 10, timeout: float = 10.0) -> ProbeResult:
    """
    获取 CPU/内存占用最高的 N 个进程。

    使用 `top -b -n1` 获取单次快照，解析为结构化数据。

    Args:
        limit: 返回进程数（默认 10）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - pid / user / cpu_percent / memory_percent / command
    """
    probe_name = "system_top"
    stdout, rc, err = await _run_command("top", "-b", "-n", "1", timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    processes = []
    in_process_section = False

    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # top 的进程列表以 "PID" 开头
        if line.startswith("PID"):
            in_process_section = True
            continue

        if not in_process_section:
            continue

        parts = line.split()
        if len(parts) < 12:
            continue

        # top -b -n1 格式（默认列）：
        # PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND
        try:
            pid = int(parts[0])
            user = parts[1]
            cpu_percent = float(parts[8])
            mem_percent = float(parts[9])
            command = " ".join(parts[11:])
        except (ValueError, IndexError):
            continue

        processes.append({
            "pid": pid,
            "user": user,
            "cpu_percent": cpu_percent,
            "memory_percent": mem_percent,
            "command": command,
        })

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=processes[:limit],
    )


async def memory_usage(timeout: float = 5.0) -> ProbeResult:
    """
    获取系统内存用量。

    使用 `free -b` 以字节为单位输出。

    Returns:
        ProbeResult.data 为 dict：
        - total / used / free / shared / buff_cache / available
    """
    probe_name = "memory_usage"
    stdout, rc, err = await _run_command("free", "-b", timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    lines = stdout.strip().split("\n")
    if len(lines) < 2:
        return _make_result(probe_name, ProbeStatus.ERROR, error="无法解析 free 输出")

    # 第一行是表头：              total        used        free      shared  buff/cache   available
    # 第二行是 Mem:  ...
    mem_line = lines[1]
    parts = mem_line.split()
    if len(parts) < 7:
        return _make_result(probe_name, ProbeStatus.ERROR, error="free 输出格式异常")

    try:
        data = {
            "total": int(parts[1]),
            "used": int(parts[2]),
            "free": int(parts[3]),
            "shared": int(parts[4]),
            "buff_cache": int(parts[5]),
            "available": int(parts[6]),
        }
    except (ValueError, IndexError) as e:
        return _make_result(probe_name, ProbeStatus.ERROR, error=f"解析内存数据失败: {e}")

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=data)


async def system_uptime(timeout: float = 5.0) -> ProbeResult:
    """
    获取系统负载与运行时长。

    使用 `uptime` 和 `cat /proc/uptime` 获取信息。

    Returns:
        ProbeResult.data 为 dict：
        - load_1m / load_5m / load_15m / uptime_seconds / uptime_human
    """
    probe_name = "system_uptime"

    # uptime 命令
    stdout, rc, err = await _run_command("uptime", timeout=timeout)
    if rc != 0 or stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    # 解析负载： load average: 0.52, 0.58, 0.59
    load_match = re.search(r"load average[s]?:\s+([\d.]+),?\s+([\d.]+),?\s+([\d.]+)", stdout)
    load_1m = float(load_match.group(1)) if load_match else 0.0
    load_5m = float(load_match.group(2)) if load_match else 0.0
    load_15m = float(load_match.group(3)) if load_match else 0.0

    # 从 /proc/uptime 获取精确秒数
    uptime_stdout, rc2, _ = await _run_command("cat", "/proc/uptime", timeout=timeout)
    uptime_seconds = 0.0
    if rc2 == 0 and uptime_stdout:
        try:
            uptime_seconds = float(uptime_stdout.strip().split()[0])
        except (ValueError, IndexError):
            pass

    # 格式化人类可读时长
    uptime_human = _format_uptime(uptime_seconds)

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data={
            "load_1m": load_1m,
            "load_5m": load_5m,
            "load_15m": load_15m,
            "uptime_seconds": round(uptime_seconds, 2),
            "uptime_human": uptime_human,
        },
    )


async def system_vmstat(count: int = 3, interval: int = 1, timeout: float = 15.0) -> ProbeResult:
    """
    获取系统整体状态采样（vmstat）。

    使用 `vmstat <interval> <count>` 获取多轮采样。

    Args:
        count: 采样次数（默认 3）
        interval: 采样间隔秒数（默认 1）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - procs_r / procs_b / memory_swap / memory_free / memory_buff / memory_cache
        - swap_si / swap_so / io_bi / io_bo / system_in / system_cs
        - cpu_us / cpu_sy / cpu_id / cpu_wa / cpu_st
    """
    probe_name = "system_vmstat"

    # vmstat 1 3 输出：第一行是表头，第二行是自启动以来的平均值，后续是采样值
    stdout, rc, err = await _run_command(
        "vmstat", str(interval), str(count + 1), timeout=timeout
    )

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    lines = stdout.strip().split("\n")
    samples = []

    # 跳过前2行（表头 + 平均值），取实际采样
    for line in lines[2:]:
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 17:
            continue

        try:
            samples.append({
                "procs_r": int(parts[0]),
                "procs_b": int(parts[1]),
                "memory_swap": int(parts[2]),
                "memory_free": int(parts[3]),
                "memory_buff": int(parts[4]),
                "memory_cache": int(parts[5]),
                "swap_si": int(parts[6]),
                "swap_so": int(parts[7]),
                "io_bi": int(parts[8]),
                "io_bo": int(parts[9]),
                "system_in": int(parts[10]),
                "system_cs": int(parts[11]),
                "cpu_us": int(parts[12]),
                "cpu_sy": int(parts[13]),
                "cpu_id": int(parts[14]),
                "cpu_wa": int(parts[15]),
                "cpu_st": int(parts[16]),
            })
        except (ValueError, IndexError):
            continue

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=samples)


# ============================================================
#  内部辅助函数
# ============================================================

def _format_uptime(seconds: float) -> str:
    """将秒数格式化为人类可读的时长字符串。"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)

    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0 or not parts:
        parts.append(f"{minutes}分钟")

    return "".join(parts)


__all__ = [
    "system_top",
    "memory_usage",
    "system_uptime",
    "system_vmstat",
]
