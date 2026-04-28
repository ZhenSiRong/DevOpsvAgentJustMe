"""
安全审计探针模块 — SELinux 状态、登录失败记录。

提供的接口：
- selinux_status()            → SELinux 状态
- failed_logins(limit)        → 失败登录记录
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


async def selinux_status(timeout: float = 5.0) -> ProbeResult:
    """
    获取 SELinux 状态。

    使用 `sestatus` 和 `getenforce`。

    Returns:
        ProbeResult.data 为 dict：
        - mode (Enforcing/Permissive/Disabled)
        - status_enabled (true/false)
        - policy_name / policy_version / current_mode
    """
    probe_name = "selinux_status"

    # 先尝试 getenforce（最简单）
    stdout, rc, err = await _run_command("getenforce", timeout=timeout)
    mode = "unknown"
    if rc == 0 and stdout:
        mode = stdout.strip()

    # 再尝试 sestatus 获取更详细信息
    stdout2, rc2, _ = await _run_command("sestatus", timeout=timeout)
    data = {
        "mode": mode,
        "status_enabled": mode.lower() in ("enforcing", "permissive"),
        "policy_name": "",
        "policy_version": "",
        "current_mode": mode,
    }

    if rc2 == 0 and stdout2:
        for line in stdout2.strip().split("\n"):
            line = line.strip()
            if line.startswith("SELinux status:"):
                val = line.split(":", 1)[1].strip()
                data["status_enabled"] = val.lower() == "enabled"
            elif line.startswith("Current mode:"):
                data["current_mode"] = line.split(":", 1)[1].strip()
            elif line.startswith("Mode from config file:"):
                data["mode_from_config"] = line.split(":", 1)[1].strip()
            elif line.startswith("Loaded policy name:"):
                data["policy_name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Policy version:"):
                data["policy_version"] = line.split(":", 1)[1].strip()

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=data)


async def failed_logins(limit: int = 20, timeout: float = 5.0) -> ProbeResult:
    """
    获取失败登录记录。

    使用 `lastb -n`。

    Args:
        limit: 最大返回记录数
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - user / terminal / origin / date / status
    """
    probe_name = "failed_logins"
    stdout, rc, err = await _run_command("lastb", "-n", str(limit), timeout=timeout)

    # lastb 可能返回 0 但无输出（没有失败记录）
    if rc != 0 or stdout is None:
        # 如果文件不存在或无权限，返回空列表而非错误
        if "No such file" in (err or "") or "Permission denied" in (err or ""):
            return _make_result(probe_name, ProbeStatus.SUCCESS, data=[])
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    entries = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("btmp") or line.startswith("wtmp"):
            continue

        # lastb 输出格式：
        # username  pts/0    192.168.1.1     Mon Apr 21 08:00 - 08:00  (00:00)
        parts = line.split(None, 5)
        if len(parts) < 4:
            continue

        entries.append({
            "user": parts[0],
            "terminal": parts[1],
            "origin": parts[2],
            "date": " ".join(parts[3:5]) if len(parts) >= 5 else parts[3],
            "status": "failed",
        })

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=entries)


__all__ = [
    "selinux_status",
    "failed_logins",
]
