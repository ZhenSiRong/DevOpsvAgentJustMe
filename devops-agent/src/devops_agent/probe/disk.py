"""
磁盘探针模块 — 感知系统磁盘使用情况。

提供的接口：
- disk_usage()          → 各分区的使用率列表
- large_files(path, n)  → 目录下最大的 N 个文件
"""

from __future__ import annotations

import re

from .base import (
    DiskUsageResult,
    LargeFileResult,
    ProbeResult,
    ProbeStatus,
    ProbeTimeoutError,
    _run_command,
    _make_result,
)


async def disk_usage(timeout: float = 30.0) -> ProbeResult:
    """
    获取所有挂载分区的磁盘使用情况。

    使用 `df -B1` 以字节为单位输出，解析为结构化数据。

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - filesystem: 文件系统标识
        - total / used / available: 字节数
        - usage_percent: 使用百分比 (0~100)
        - mount_point: 挂载点
    """
    probe_name = "disk_usage"
    stdout, rc, err = await _run_command("df", "-B1", timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    if stdout is None:
        # 超时或异常
        if "超时" in err or "timeout" in err.lower():
            return _make_result(probe_name, ProbeStatus.TIMEOUT, error=err)
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    partitions = []
    lines = stdout.strip().split("\n")

    for line in lines[1:]:  # 跳过表头
        line = line.strip()
        if not line:
            continue

        # df -B1 输出格式：Filesystem 1B-blocks Used Available Use% Mounted on
        parts = line.split()
        if len(parts) < 6:
            continue

        try:
            usage_str = parts[4].rstrip("%")
            usage_percent = float(usage_str) if usage_str.replace(".", "").isdigit() else 0.0
        except ValueError:
            usage_percent = 0.0

        partition = DiskUsageResult(
            filesystem=parts[0],
            total=_safe_int(parts[1]),
            used=_safe_int(parts[2]),
            available=_safe_int(parts[3]),
            usage_percent=usage_percent,
            mount_point=parts[5] if len(parts) > 5 else "",
        )
        partitions.append(partition.to_dict())

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=partitions,
    )


async def large_files(path: str = "/var/log", top_n: int = 10, timeout: float = 30.0) -> ProbeResult:
    """
    扫描指定目录下体积最大的 N 个文件。

    实现策略：用 `du -a` + 排序取 top N。
    注意：对大目录可能较慢，建议配合 timeout 参数。

    Args:
        path: 目标路径（默认 /var/log）
        top_n: 返回前 N 个大文件
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，按 size_bytes 降序排列，每项含 path 和 size_bytes
    """
    probe_name = "large_files"

    # 用 du -ab 获取所有文件大小（字节级精度）
    stdout, rc, err = await _run_command("du", "-ab", "--max-depth=1", path, timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    if stdout is None:
        if "超时" in err or "timeout" in err.lower():
            return _make_result(probe_name, ProbeStatus.TIMEOUT, error=err)
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    files = []
    lines = stdout.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # du 输出格式：size_bytes\tfilepath
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            size_bytes = int(match.group(1))
            filepath = match.group(2).strip()
            # 跳过目录自身汇总行（通常以目标路径结尾且无扩展名）
            files.append(LargeFileResult(
                path=filepath,
                size_bytes=size_bytes,
            ).to_dict())

    # 按大小降序排列，取 top_n
    files.sort(key=lambda x: x["size_bytes"], reverse=True)

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=files[:top_n],
    )


def _safe_int(value: str) -> int:
    """安全地将字符串转换为整数"""
    try:
        return int(value)
    except ValueError:
        return 0


__all__ = [
    "disk_usage",
    "large_files",
]
