"""
日志分析扩展探针 — dmesg、日志切片。

提供的接口：
- kernel_messages(level)      → 内核日志
- log_slice(path, start, end) → 按行号范围提取日志
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


async def kernel_messages(level: str | None = None, lines: int = 100, timeout: float = 10.0) -> ProbeResult:
    """
    获取内核环形缓冲日志（dmesg）。

    Args:
        level: 日志级别过滤（如 "err,warn"）
        lines: 最大返回行数
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - timestamp / level / facility / message
    """
    probe_name = "kernel_messages"

    cmd = ["dmesg", "--time=iso", "--nopager"]
    if level:
        cmd.extend(["--level", level])

    stdout, rc, err = await _run_command(*cmd, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    entries = []
    for line in stdout.strip().split("\n")[:lines]:
        line = line.strip()
        if not line:
            continue

        # dmesg --time=iso 常见格式：
        # 1) 带 facility/level: 2026-04-28T10:00:00+08:00 kern :warn : message
        # 2) 纯消息:          2026-04-28T10:00:00,123456+08:00 message here
        # 3) 无时间戳:         message here
        iso_match = re.match(
            r"^(\d{4}-\d{2}-\d{2}T[\d:.,+\-]+)\s+(\S+)\s*:(\S+)\s*:\s*(.+)$",
            line,
        )
        if iso_match:
            entries.append({
                "timestamp": iso_match.group(1),
                "facility": iso_match.group(2).strip(),
                "level": iso_match.group(3).strip(),
                "message": iso_match.group(4).strip(),
            })
            continue

        # 尝试仅匹配时间戳 + 消息
        ts_match = re.match(
            r"^(\d{4}-\d{2}-\d{2}T[\d:.,+\-]+)\s+(.+)$",
            line,
        )
        if ts_match:
            entries.append({
                "timestamp": ts_match.group(1),
                "facility": "kern",
                "level": "",
                "message": ts_match.group(2).strip(),
            })
            continue

        # 无法识别的格式，原样返回
        entries.append({
            "timestamp": "",
            "facility": "",
            "level": "",
            "message": line,
        })

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=entries[:lines])


async def log_slice(path: str, start_line: int = 1, end_line: int | None = None, timeout: float = 10.0) -> ProbeResult:
    """
    按行号范围提取日志文件内容。

    使用 `sed -n 'start,endp'`。

    Args:
        path: 日志文件路径
        start_line: 起始行号（1-based，默认 1）
        end_line: 结束行号（None 则提取到文件末尾）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含 line_number / content
    """
    probe_name = "log_slice"

    if end_line is None:
        range_str = f"{start_line},$p"
    else:
        range_str = f"{start_line},{end_line}p"

    stdout, rc, err = await _run_command("sed", "-n", range_str, path, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    result_lines = []
    for i, raw in enumerate(stdout.strip().split("\n")):
        result_lines.append({
            "line_number": start_line + i,
            "content": raw,
        })

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=result_lines,
        summary={
            "total_returned": len(result_lines),
            "start_line": start_line,
            "end_line": end_line,
        },
    )


__all__ = [
    "kernel_messages",
    "log_slice",
]
