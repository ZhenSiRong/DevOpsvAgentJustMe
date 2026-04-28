"""
进程管理扩展探针 — 进程查找、进程树、打开文件。

提供的接口：
- process_find(pattern)       → 按名查找 PID
- process_tree()              → 进程树
- list_open_files(pid, port, path) → 打开文件/端口
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


async def process_find(pattern: str, timeout: float = 10.0) -> ProbeResult:
    """
    按名称模式查找进程 PID。

    使用 `pgrep -a`。

    Args:
        pattern: 进程名匹配模式
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含 pid / command
    """
    probe_name = "process_find"
    stdout, rc, err = await _run_command("pgrep", "-a", pattern, timeout=timeout)

    if rc != 0:
        # pgrep 返回 1 表示没有匹配（不是错误）
        if rc == 1:
            return _make_result(probe_name, ProbeStatus.SUCCESS, data=[])
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    results = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        parts = line.split(None, 1)
        if not parts:
            continue

        try:
            pid = int(parts[0])
        except ValueError:
            continue

        results.append({
            "pid": pid,
            "command": parts[1] if len(parts) > 1 else "",
        })

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=results)


async def process_tree(timeout: float = 10.0) -> ProbeResult:
    """
    获取进程树。

    使用 `pstree -p`。

    Args:
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 dict：
        - tree_text: pstree 原始文本输出
        - processes: list[dict] 扁平化的进程列表（pid / parent_pid / command）
    """
    probe_name = "process_tree"
    stdout, rc, err = await _run_command("pstree", "-p", timeout=timeout)

    if rc != 0 or stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    # 同时用 ps 获取父子关系
    ps_stdout, ps_rc, _ = await _run_command(
        "ps", "-eo", "pid,ppid,comm", "--no-headers", timeout=timeout
    )

    processes = []
    if ps_rc == 0 and ps_stdout:
        for line in ps_stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    processes.append({
                        "pid": int(parts[0]),
                        "parent_pid": int(parts[1]),
                        "command": parts[2],
                    })
                except ValueError:
                    continue

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data={
            "tree_text": stdout.strip(),
            "processes": processes,
        },
    )


async def list_open_files(
    pid: int | None = None,
    port: int | None = None,
    path: str | None = None,
    timeout: float = 15.0,
) -> ProbeResult:
    """
    列出进程打开的文件/端口/连接。

    使用 `lsof`。

    Args:
        pid: 按进程 PID 过滤
        port: 按端口号过滤
        path: 按文件路径过滤
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - command / pid / user / fd / type / device / size / node / name
    """
    probe_name = "list_open_files"

    cmd = ["lsof", "-F", "cnupftDdsN"]

    if pid is not None:
        cmd.extend(["-p", str(pid)])
    if port is not None:
        cmd.extend(["-i", f":{port}"])
    if path is not None:
        cmd.append(path)

    stdout, rc, err = await _run_command(*cmd, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    # lsof -F 输出格式：每行一个字段，以字母开头标识字段类型
    # c=command, n=name, p=pid, u=user, f=fd, t=type, D=device, s=size, N=node
    entries = []
    current: dict[str, Any] = {}

    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        if len(line) < 2:
            continue

        field_type = line[0]
        value = line[1:]

        if field_type == "p" and current:
            # 新的进程记录开始，保存旧的
            entries.append(current)
            current = {}

        mapping = {
            "c": "command",
            "n": "name",
            "p": "pid",
            "u": "user",
            "f": "fd",
            "t": "type",
            "D": "device",
            "s": "size",
            "N": "node",
        }

        if field_type in mapping:
            current[mapping[field_type]] = value

    if current:
        entries.append(current)

    # 转换 pid 为整数
    for e in entries:
        try:
            e["pid"] = int(e.get("pid", 0))
        except ValueError:
            e["pid"] = 0
        try:
            e["size"] = int(e.get("size", 0))
        except ValueError:
            e["size"] = 0

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=entries)


__all__ = [
    "process_find",
    "process_tree",
    "list_open_files",
]
