"""
文件系统探针模块 — 目录大小、IO统计、块设备、文件查询等。

提供的接口：
- directory_size(path, depth)     → 目录大小及子目录分布
- disk_iostat(samples)            → 磁盘 IO 统计
- block_devices()                 → 块设备信息
- list_directory(path)            → 列出目录内容
- find_files(path, name, size, mtime) → 文件搜索
- file_stat(path)                 → 文件元信息
- file_type(path)                 → 文件类型检测
- read_file(path, lines, offset)  → 读取文件内容
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


async def directory_size(path: str = "/var/log", depth: int = 1, timeout: float = 30.0) -> ProbeResult:
    """
    获取指定目录的总大小及子目录分布。

    使用 `du -h --max-depth=<depth>`。

    Args:
        path: 目标目录
        depth: 递归深度（默认 1）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 dict：
        - total: 总大小（人类可读）
        - entries: list[dict] 子项（path / size_human / size_bytes）
    """
    probe_name = "directory_size"
    stdout, rc, err = await _run_command(
        "du", "-h", "--max-depth", str(depth), path, timeout=timeout
    )

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    entries = []
    total_human = ""
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # du -h 输出格式：size\tpath
        match = re.match(r"^([\d.]+[KMGTP]?)\s+(.+)$", line)
        if not match:
            continue

        size_human = match.group(1)
        filepath = match.group(2).strip()

        if filepath == path or filepath.rstrip("/") == path.rstrip("/"):
            total_human = size_human
        else:
            entries.append({
                "path": filepath,
                "size_human": size_human,
            })

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data={
            "target": path,
            "total_human": total_human,
            "entries": entries,
        },
    )


async def disk_iostat(samples: int = 3, interval: int = 1, timeout: float = 15.0) -> ProbeResult:
    """
    获取磁盘 IO 统计。

    使用 `iostat -x <interval> <count>`。

    Args:
        samples: 采样次数（默认 3）
        interval: 采样间隔秒数（默认 1）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - device / rrqm_s / wrqm_s / r_s / w_s / rkB_s / wkB_s
        - avgrq_sz / avgqu_sz / await / r_await / w_await / svctm / util_percent
    """
    probe_name = "disk_iostat"
    stdout, rc, err = await _run_command(
        "iostat", "-x", str(interval), str(samples), timeout=timeout
    )

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    devices = []
    in_device_section = False

    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # iostat -x 中设备列表以 "Device" 开头
        if line.startswith("Device"):
            in_device_section = True
            continue

        if not in_device_section:
            continue

        parts = line.split()
        if len(parts) < 14:
            continue

        try:
            devices.append({
                "device": parts[0],
                "rrqm_s": float(parts[1]),
                "wrqm_s": float(parts[2]),
                "r_s": float(parts[3]),
                "w_s": float(parts[4]),
                "rkB_s": float(parts[5]),
                "wkB_s": float(parts[6]),
                "avgrq_sz": float(parts[7]),
                "avgqu_sz": float(parts[8]),
                "await": float(parts[9]),
                "r_await": float(parts[10]),
                "w_await": float(parts[11]),
                "svctm": float(parts[12]),
                "util_percent": float(parts[13]),
            })
        except (ValueError, IndexError):
            continue

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=devices)


async def block_devices(timeout: float = 10.0) -> ProbeResult:
    """
    获取块设备信息。

    使用 `lsblk -f --json`（如果可用）或 `lsblk -f` 文本解析。

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - name / size / type / mountpoint / fstype / label / uuid
    """
    probe_name = "block_devices"

    # 优先尝试 JSON 输出
    stdout, rc, err = await _run_command("lsblk", "-f", "--json", timeout=timeout)
    if rc == 0 and stdout:
        try:
            import json
            parsed = json.loads(stdout)
            devices = _flatten_lsblk_json(parsed.get("blockdevices", []))
            return _make_result(probe_name, ProbeStatus.SUCCESS, data=devices)
        except (json.JSONDecodeError, KeyError):
            pass

    # 回退到文本解析
    stdout, rc, err = await _run_command("lsblk", "-f", timeout=timeout)
    if rc != 0 or stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    devices = []
    lines = stdout.strip().split("\n")
    if len(lines) < 2:
        return _make_result(probe_name, ProbeStatus.ERROR, error="lsblk 输出异常")

    # 表头行用于确定列位置
    header = lines[0]
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        # lsblk -f 输出：NAME FSTYPE LABEL UUID FSAVAIL FSUSE% MOUNTPOINT
        # 简单按空白分割，第一列为设备名
        parts = line.split()
        if not parts:
            continue

        devices.append({
            "name": parts[0],
            "fstype": parts[1] if len(parts) > 1 else "",
            "label": parts[2] if len(parts) > 2 else "",
            "uuid": parts[3] if len(parts) > 3 else "",
            "mountpoint": parts[-1] if len(parts) > 6 else "",
        })

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=devices)


async def list_directory(path: str = "/", timeout: float = 10.0) -> ProbeResult:
    """
    列出目录内容。

    使用 `ls -la --time-style=iso`。

    Args:
        path: 目标目录
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - name / type / permissions / owner / group / size / mtime
    """
    probe_name = "list_directory"
    stdout, rc, err = await _run_command(
        "ls", "-la", "--time-style=iso", path, timeout=timeout
    )

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    entries = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("total") or line.startswith("总计"):
            continue

        # ls -la 输出格式（8~9列）：
        # perms links owner group size mtime(2col) name
        # 使用 maxsplit=7 保留完整文件名（含空格）
        parts = line.split(None, 7)
        if len(parts) < 7:
            continue

        perms = parts[0]
        entry_type = "directory" if perms.startswith("d") else "symlink" if perms.startswith("l") else "file"

        # mtime 占 1 列（iso 日期时间）或 2 列（月 日 时:分 / 年）
        if len(parts) == 7:
            # iso 格式: 2026-04-28 17:59 或 04-28 17:59
            mtime = parts[4]
            name = parts[6]
        elif len(parts) == 8:
            # 标准格式: Apr 28 17:59 name
            mtime = f"{parts[4]} {parts[5]}"
            name = parts[7]
        else:
            mtime = f"{parts[4]} {parts[5]}"
            name = parts[-1]

        entries.append({
            "permissions": perms,
            "type": entry_type,
            "owner": parts[1] if len(parts) >= 7 else parts[2],
            "group": parts[2] if len(parts) >= 7 else parts[3],
            "size": parts[3] if len(parts) >= 7 else parts[4],
            "mtime": mtime,
            "name": name,
        })

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=entries)


async def find_files(
    path: str = "/",
    name: str | None = None,
    ftype: str | None = None,
    size: str | None = None,
    mtime: int | None = None,
    limit: int = 100,
    timeout: float = 30.0,
) -> ProbeResult:
    """
    搜索文件。

    使用 `find` 命令，支持按名称、类型、大小、修改时间过滤。

    Args:
        path: 搜索起始路径
        name: 文件名模式（如 *.log）
        ftype: 文件类型（f=文件, d=目录, l=链接）
        size: 大小条件（如 +100M, -1G）
        mtime: 修改天数（如 +7 表示 7 天前）
        limit: 最大返回数量
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含 path / size / mtime
    """
    probe_name = "find_files"

    cmd = ["find", path, "-maxdepth", "3"]

    if ftype:
        cmd.extend(["-type", ftype])
    if name:
        cmd.extend(["-name", name])
    if size:
        cmd.extend(["-size", size])
    if mtime is not None:
        cmd.extend(["-mtime", str(mtime)])

    cmd.extend(["-printf", "%p\\t%s\\t%TY-%Tm-%Td %TH:%TM\\n"])

    stdout, rc, err = await _run_command(*cmd, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    results = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 3:
            continue

        try:
            size_bytes = int(parts[1])
        except ValueError:
            size_bytes = 0

        results.append({
            "path": parts[0],
            "size_bytes": size_bytes,
            "mtime": parts[2],
        })

        if len(results) >= limit:
            break

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=results)


async def file_stat(path: str, timeout: float = 5.0) -> ProbeResult:
    """
    获取文件元信息。

    使用 `stat` 命令。

    Args:
        path: 目标文件路径
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 dict：
        - size / permissions / owner / group / inode / links / access_time / modify_time / change_time
    """
    probe_name = "file_stat"

    # 使用 stat --format 获取结构化输出
    fmt = "%s\t%a\t%U\t%G\t%i\t%h\t%X\t%Y\t%Z\t%F"
    stdout, rc, err = await _run_command("stat", "--format", fmt, path, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    parts = stdout.strip().split("\t")
    if len(parts) < 10:
        return _make_result(probe_name, ProbeStatus.ERROR, error="stat 输出格式异常")

    try:
        data = {
            "path": path,
            "size_bytes": int(parts[0]),
            "permissions": parts[1],
            "owner": parts[2],
            "group": parts[3],
            "inode": int(parts[4]),
            "links": int(parts[5]),
            "access_time": int(parts[6]),
            "modify_time": int(parts[7]),
            "change_time": int(parts[8]),
            "file_type": parts[9],
        }
    except (ValueError, IndexError) as e:
        return _make_result(probe_name, ProbeStatus.ERROR, error=f"解析 stat 输出失败: {e}")

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=data)


async def file_type(path: str, timeout: float = 5.0) -> ProbeResult:
    """
    检测文件类型。

    使用 `file` 命令。

    Args:
        path: 目标文件路径
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 dict：path / description
    """
    probe_name = "file_type"
    stdout, rc, err = await _run_command("file", "-b", path, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data={
            "path": path,
            "description": stdout.strip(),
        },
    )


async def read_file(
    path: str,
    lines: int | None = None,
    offset: int = 0,
    timeout: float = 10.0,
) -> ProbeResult:
    """
    读取文件内容。

    使用 `sed -n 'start,endp'` 或 `head/tail` 组合。

    Args:
        path: 目标文件路径
        lines: 读取行数（None 则读取全部，但限制 500 行）
        offset: 起始行偏移（0-based）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含 line_number / content
    """
    probe_name = "read_file"

    if lines is None:
        lines = 500  # 默认安全限制

    end_line = offset + lines
    stdout, rc, err = await _run_command(
        "sed", "-n", f"{offset + 1},{end_line}p", path, timeout=timeout
    )

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)
    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    result_lines = []
    for i, raw in enumerate(stdout.strip().split("\n")):
        result_lines.append({
            "line_number": offset + i + 1,
            "content": raw,
        })

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=result_lines,
        summary={
            "total_returned": len(result_lines),
            "offset": offset,
            "requested_lines": lines,
        },
    )


# ============================================================
#  内部辅助函数
# ============================================================

def _flatten_lsblk_json(devices: list[dict]) -> list[dict]:
    """将 lsblk --json 的嵌套结构展平为列表。"""
    result = []
    for dev in devices:
        entry = {
            "name": dev.get("name", ""),
            "size": dev.get("size", ""),
            "type": dev.get("type", ""),
            "mountpoint": dev.get("mountpoint") or "",
            "fstype": dev.get("fstype") or "",
            "label": dev.get("label") or "",
            "uuid": dev.get("uuid") or "",
        }
        result.append(entry)

        children = dev.get("children", [])
        if children:
            result.extend(_flatten_lsblk_json(children))

    return result


__all__ = [
    "directory_size",
    "disk_iostat",
    "block_devices",
    "list_directory",
    "find_files",
    "file_stat",
    "file_type",
    "read_file",
]
