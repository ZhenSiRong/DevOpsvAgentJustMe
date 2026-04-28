"""
服务管理探针模块 — systemd 服务状态查询。

提供的接口：
- service_status(service)     → 单个服务状态
- service_list(state, type)   → 服务列表
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


async def service_status(service: str, timeout: float = 10.0) -> ProbeResult:
    """
    获取单个 systemd 服务的详细状态。

    使用 `systemctl status <service>`。

    Args:
        service: 服务名（如 "nginx", "sshd"）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 dict：
        - name / active_state / load_state / sub_state / description
        - pid / main_pid / memory / cpu_usage / uptime
        - recent_logs: list[str] 最近几条日志
    """
    probe_name = "service_status"
    stdout, rc, err = await _run_command(
        "systemctl", "status", service, "--no-pager", timeout=timeout
    )

    # systemctl status 返回码：0=active, 3=inactive/failed, 其他=错误
    if rc not in (0, 3) or stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err or stdout)

    data = _parse_systemctl_status(stdout, service)

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=data,
    )


async def service_list(
    state: str | None = None,
    service_type: str = "service",
    timeout: float = 10.0,
) -> ProbeResult:
    """
    列出 systemd 服务单元。

    使用 `systemctl list-units`。

    Args:
        state: 状态过滤（如 "running", "failed", "active"）
        service_type: 单元类型（默认 "service"）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - name / load_state / active_state / sub_state / description
    """
    probe_name = "service_list"

    cmd = [
        "systemctl", "list-units",
        "--type", service_type,
        "--no-pager", "--no-legend",
    ]
    if state:
        cmd.extend(["--state", state])

    stdout, rc, err = await _run_command(*cmd, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    services = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # list-units 输出格式：
        # UNIT                     LOAD   ACTIVE SUB     DESCRIPTION
        # nginx.service            loaded active running A high performance web server
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue

        services.append({
            "name": parts[0],
            "load_state": parts[1],
            "active_state": parts[2],
            "sub_state": parts[3],
            "description": parts[4] if len(parts) > 4 else "",
        })

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=services)


# ============================================================
#  内部解析函数
# ============================================================

def _parse_systemctl_status(stdout: str, service_name: str) -> dict[str, Any]:
    """解析 systemctl status 的文本输出。"""
    lines = stdout.split("\n")
    data: dict[str, Any] = {
        "name": service_name,
        "active_state": "unknown",
        "load_state": "unknown",
        "sub_state": "unknown",
        "description": "",
        "pid": None,
        "main_pid": None,
        "memory": None,
        "cpu_usage": None,
        "uptime": None,
        "recent_logs": [],
    }

    in_log_section = False

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # 第一行通常包含服务名和描述
        if line_stripped.startswith("\u25cf"):
            desc_match = re.match(r"\u25cf\s+\S+\s+-\s+(.+)", line_stripped)
            if desc_match:
                data["description"] = desc_match.group(1).strip()

        # Loaded: loaded (/lib/systemd/system/nginx.service; enabled; vendor preset: enabled)
        elif line_stripped.startswith("Loaded:"):
            load_match = re.match(r"Loaded:\s+(\S+)", line_stripped)
            if load_match:
                data["load_state"] = load_match.group(1)

        # Active: active (running) since Mon 2026-04-21 08:00:00 CST; 2h ago
        elif line_stripped.startswith("Active:"):
            active_match = re.match(r"Active:\s+(\S+)\s*\(([^)]+)\)?", line_stripped)
            if active_match:
                data["active_state"] = active_match.group(1)
                data["sub_state"] = active_match.group(2) or ""
            else:
                simple_match = re.match(r"Active:\s+(\S+)", line_stripped)
                if simple_match:
                    data["active_state"] = simple_match.group(1)

        # Main PID: 1234 (nginx)
        elif "PID:" in line_stripped:
            pid_match = re.search(r"Main PID:\s+(\d+)", line_stripped)
            if pid_match:
                data["main_pid"] = int(pid_match.group(1))
            pid_match2 = re.search(r"PID:\s+(\d+)", line_stripped)
            if pid_match2:
                data["pid"] = int(pid_match2.group(1))

        # Memory: 1.2M
        elif line_stripped.startswith("Memory:"):
            mem_match = re.match(r"Memory:\s+(.+)", line_stripped)
            if mem_match:
                data["memory"] = mem_match.group(1).strip()

        # CPU: 12ms
        elif line_stripped.startswith("CPU:"):
            cpu_match = re.match(r"CPU:\s+(.+)", line_stripped)
            if cpu_match:
                data["cpu_usage"] = cpu_match.group(1).strip()

        # 日志行以 4 空格缩进开头
        elif line.startswith("     ") and not line_stripped.startswith("Loaded:"):
            in_log_section = True
            data["recent_logs"].append(line_stripped)

    return data


__all__ = [
    "service_status",
    "service_list",
]
