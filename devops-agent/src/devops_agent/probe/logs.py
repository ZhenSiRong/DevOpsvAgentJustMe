"""
日志探针模块 — 读取系统日志和应用程序日志。

提供的接口：
- journal_logs(service, lines) → journalctl 日志查询
- tail_file(path, lines)      → 文件尾部读取（通用）
- grep_log(pattern, path)     → 日志内容搜索
"""

from __future__ import annotations

import re

from .base import (
    LogEntry,
    ProbeResult,
    ProbeStatus,
    _run_command,
    _make_result,
)


async def journal_logs(
    service: str | None = None,
    lines: int = 50,
    since: str | None = None,
    until: str | None = None,
    timeout: float = 30.0,
) -> ProbeResult:
    """
    通过 journalctl 查询 systemd 日志。

    Args:
        service: 可选的服务名过滤（如 "nginx", "mysqld"）
        lines: 返回的最大行数
        since: 时间范围起始（如 "1 hour ago" 或 "2026-04-21 08:00"）
        until: 时间范围结束
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - timestamp / source / message / priority
    """
    probe_name = "journal_logs"

    # 构建命令参数
    cmd_args = [
        "journalctl",
        "--no-pager",
        "-n", str(lines),
        "--output=short-iso",
    ]

    if service:
        cmd_args.extend(["-u", service])
    if since:
        cmd_args.extend(["--since", since])
    if until:
        cmd_args.extend(["--until", until])

    stdout, rc, err = await _run_command(*cmd_args, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    entries = []
    lines_list = stdout.strip().split("\n")

    for line in lines_list:
        line = line.strip()
        if not line or line.startswith("--"):
            continue  # 跳过空行和时间范围标记

        entry = _parse_journal_line(line, service)
        if entry:
            entries.append(entry.to_dict())

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=entries,
    )


async def tail_file(
    path: str,
    lines: int = 50,
    follow: bool = False,
    timeout: float = 10.0,
) -> ProbeResult:
    """
    通用文件尾部读取。

    使用 `tail -n` 读取文件末尾 N 行。
    不支持 follow 模式的持续输出（需要 WebSocket 推送，由 API 层处理）。

    Args:
        path: 目标文件路径
        lines: 读取行数
        follow: 是否跟踪模式（暂不支持，保留参数）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含 line_number / content / raw_line
    """
    probe_name = "tail_file"

    stdout, rc, err = await _run_command("tail", "-n", str(lines), path, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    result_lines = []
    raw_lines = stdout.strip().split("\n")

    for i, raw in enumerate(raw_lines):
        result_lines.append({
            "line_number": i + 1,
            "content": raw,
            "raw_line": raw,
        })

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=result_lines,
    )


async def grep_log(
    pattern: str,
    path: str | None = None,
    context_before: int = 0,
    context_after: int = 0,
    timeout: float = 15.0,
) -> ProbeResult:
    """
    在日志文件或 journalctl 输出中搜索匹配的行。

    Args:
        pattern: 正则表达式或字符串
        path: 目标文件路径（如果为 None 则从 journalctl 搜索）
        context_before: 匹配行前显示多少行上下文
        context_after: 匹配行后显示多少行上下文
        timeout: 超时时间

    Returns:
        ProbeResult.data 为 list[dict]，含 matched_line / match_content / context_before / context_after
    """
    probe_name = "grep_log"

    if path:
        # 文件内搜索：grep -C
        args = ["grep", "-n"]
        if context_before > 0 or context_after > 0:
            max_ctx = max(context_before, context_after)
            args.extend(["-C", str(max_ctx)])
        args.extend([pattern, path])

        stdout, rc, err = await _run_command(*args, timeout=timeout)
    else:
        # 从 journalctl 搜索
        args = ["journalctl", "--no-pager", "-g", pattern]
        stdout, rc, err = await _run_command(*args, timeout=timeout)

    if rc != 0 and rc == 2:
        # grep 返回码 2 表示没有匹配行（不是错误）
        return _make_result(probe_name, ProbeStatus.SUCCESS, data=[])

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    matches = []
    for raw_line in stdout.strip().split("\n"):
        if not raw_line.strip():
            continue
        matches.append({
            "match_content": raw_line.strip(),
            "pattern": pattern,
        })

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=matches,
    )


# ============================================================
#  内部解析函数
# ============================================================

def _parse_journal_line(line: str, default_source: str | None = None) -> LogEntry | None:
    """
    解析 journalctl --output=short-iso 格式的单行日志。

    short-iso 格式示例：
    Apr 21 16:55:01 server nginx[1234]: GET /api/health 200

    包含 ISO 时间戳的格式：
    2026-04-21T16:55:01+08:00 server nginx[1234]: message here
    """
    if not line:
        return None

    # 尝试解析带时间戳的格式（journalctl --output=short-precise）
    iso_match = re.match(
        r"^(\d{4}-\d{2}-\d{2}T[\d:.+\-]+)\s+(\S+)\s+(.+)$",
        line,
    )
    if iso_match:
        timestamp_str = iso_match.group(1)
        hostname = iso_match.group(2)
        rest = iso_match.group(3)

        source, message = _split_source_message(rest, default_source)

        return LogEntry(
            timestamp=timestamp_str,
            source=source or hostname,
            message=message,
            priority=_detect_priority(message),
        )

    # 传统 syslog 格式：Mon DD HH:MM:SS hostname process[pid]: message
    traditional_match = re.match(
        r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.+)$",
        line,
    )
    if traditional_match:
        timestamp_str = traditional_match.group(1)
        hostname = traditional_match.group(2)
        rest = traditional_match.group(3)

        source, message = _split_source_message(rest, default_source)

        return LogEntry(
            timestamp=f"2026-{timestamp_str}",  # 补全年份
            source=source or hostname,
            message=message,
            priority=_detect_priority(message),
        )

    # 无法识别的格式：原样返回
    return LogEntry(
        timestamp="",
        source=default_source,
        message=line,
    )


def _split_source_message(rest: str, default_source: str | None) -> tuple[str | None, str]:
    """
    从 "process[pid]: message" 中拆分来源和消息内容。

    支持格式：
    - nginx[1234]: message
    - mysqld: message
    - kernel: [12345.678] message
    """
    pid_pattern = re.match(r"^([\w\-.]+)(?:\[(\d+)\])?\s*:\s*(.+)$", rest)
    if pid_pattern:
        source = pid_pattern.group(1)
        message = pid_pattern.group(3)
        return (source, message)

    return (default_source, rest)


def _detect_priority(message: str) -> str | None:
    """根据消息内容推断日志优先级。"""
    msg_lower = message.lower()

    if any(kw in msg_lower for kw in ["emerg", "panic", "fatal"]):
        return "emerg"
    elif any(kw in msg_lower for kw in ["alert", "critical"]):
        return "alert"
    elif any(kw in msg_lower for kw in ["error", "fail", "exception", "traceback"]):
        return "err"
    elif any(kw in msg_lower for kw in ["warn", "warning"]):
        return "warning"
    elif any(kw in msg_lower for kw in ["notice"]):
        return "notice"
    else:
        return "info"


__all__ = [
    "journal_logs",
    "tail_file",
    "grep_log",
]
