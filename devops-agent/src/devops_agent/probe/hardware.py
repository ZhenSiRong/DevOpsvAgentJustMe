"""
硬件信息探针模块 — CPU、内存、PCI 设备。

提供的接口：
- cpu_info()                  → CPU 信息
- memory_info()               → 内存硬件信息
- pci_devices()               → PCI 设备列表
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


async def cpu_info(timeout: float = 5.0) -> ProbeResult:
    """
    获取 CPU 信息。

    使用 `lscpu`。

    Returns:
        ProbeResult.data 为 dict：
        - architecture / model_name / vendor_id / cpu_count / cores_per_socket / threads_per_core
        - cpu_mhz / cpu_max_mhz / cache_sizes
    """
    probe_name = "cpu_info"
    stdout, rc, err = await _run_command("lscpu", timeout=timeout)

    if rc != 0 or stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    data: dict[str, Any] = {
        "architecture": "",
        "model_name": "",
        "vendor_id": "",
        "cpu_count": 0,
        "cores_per_socket": 0,
        "threads_per_core": 0,
        "sockets": 0,
        "cpu_mhz": None,
        "cpu_max_mhz": None,
        "cache_l1d": "",
        "cache_l1i": "",
        "cache_l2": "",
        "cache_l3": "",
    }

    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line or (":" not in line and "：" not in line):
            continue

        # 支持半角和全角冒号
        sep = ":" if ":" in line else "："
        key, val = line.split(sep, 1)
        key = key.strip().lower().replace(" ", "_")
        val = val.strip()

        # 支持中英文 key（麒麟系统 lscpu 输出为中文）
        if key in ("architecture", "架构"):
            data["architecture"] = val
        elif key in ("model_name", "型号名称"):
            data["model_name"] = val
        elif key in ("vendor_id", "厂商_id", "厂商id"):
            data["vendor_id"] = val
        elif key in ("cpu(s)", "cpu"):
            try:
                data["cpu_count"] = int(val)
            except ValueError:
                pass
        elif key in ("core(s)_per_socket", "每个座的核数"):
            try:
                data["cores_per_socket"] = int(val)
            except ValueError:
                pass
        elif key in ("thread(s)_per_core", "每个核的线程数"):
            try:
                data["threads_per_core"] = int(val)
            except ValueError:
                pass
        elif key in ("socket(s)", "座"):
            try:
                data["sockets"] = int(val)
            except ValueError:
                pass
        elif key in ("cpu_mhz", "cpu_mhz"):
            try:
                data["cpu_mhz"] = float(val)
            except ValueError:
                pass
        elif key in ("cpu_max_mhz",):
            try:
                data["cpu_max_mhz"] = float(val)
            except ValueError:
                pass
        elif key in ("l1d_cache",):
            data["cache_l1d"] = val
        elif key in ("l1i_cache",):
            data["cache_l1i"] = val
        elif key in ("l2_cache",):
            data["cache_l2"] = val
        elif key in ("l3_cache",):
            data["cache_l3"] = val

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=data)


async def memory_info(timeout: float = 5.0) -> ProbeResult:
    """
    获取内存硬件信息。

    使用 `lsmem`（如果可用），否则从 /proc/meminfo 获取。

    Returns:
        ProbeResult.data 为 dict：
        - total_online / total_offline / total_size / block_size / devices
    """
    probe_name = "memory_info"

    # 优先尝试 lsmem
    stdout, rc, err = await _run_command("lsmem", timeout=timeout)
    if rc == 0 and stdout:
        data = _parse_lsmem_output(stdout)
        return _make_result(probe_name, ProbeStatus.SUCCESS, data=data)

    # 回退到 /proc/meminfo
    stdout2, rc2, _ = await _run_command("cat", "/proc/meminfo", timeout=timeout)
    if rc2 == 0 and stdout2:
        mem_total = ""
        for line in stdout2.strip().split("\n"):
            if line.startswith("MemTotal:"):
                mem_total = line.split(":", 1)[1].strip()
                break

        return _make_result(
            probe_name,
            ProbeStatus.SUCCESS,
            data={
                "total_size": mem_total,
                "source": "/proc/meminfo",
                "devices": [],
            },
        )

    return _make_result(probe_name, ProbeStatus.ERROR, error="无法获取内存信息")


async def pci_devices(timeout: float = 5.0) -> ProbeResult:
    """
    获取 PCI 设备列表。

    使用 `lspci`。

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - slot / class_name / vendor / device / subsystem
    """
    probe_name = "pci_devices"
    stdout, rc, err = await _run_command("lspci", timeout=timeout)

    if rc != 0 or stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    devices = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        # lspci 格式：00:00.0 Host bridge: Intel Corporation ...
        match = re.match(r"^(\S+)\s+(.+)$", line)
        if not match:
            continue

        slot = match.group(1)
        rest = match.group(2)

        # 尝试拆分 class 和 device 描述
        class_match = re.match(r"^([^:]+):\s+(.+)$", rest)
        if class_match:
            class_name = class_match.group(1).strip()
            device_desc = class_match.group(2).strip()
        else:
            class_name = ""
            device_desc = rest

        devices.append({
            "slot": slot,
            "class_name": class_name,
            "device_description": device_desc,
        })

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=devices)


# ============================================================
#  内部解析函数
# ============================================================

def _parse_lsmem_output(stdout: str) -> dict[str, Any]:
    """解析 lsmem 输出。"""
    data = {
        "total_online": "",
        "total_offline": "",
        "total_size": "",
        "block_size": "",
        "devices": [],
        "source": "lsmem",
    }

    in_device_section = False
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("Total online memory:"):
            data["total_online"] = line.split(":", 1)[1].strip()
        elif line.startswith("Total offline memory:"):
            data["total_offline"] = line.split(":", 1)[1].strip()
        elif line.startswith("Memory block size:"):
            data["block_size"] = line.split(":", 1)[1].strip()

        # 设备列表以 SIZE 开头
        if line.startswith("SIZE"):
            in_device_section = True
            continue

        if in_device_section and line[0].isdigit():
            parts = line.split()
            if len(parts) >= 4:
                data["devices"].append({
                    "size": parts[0],
                    "state": parts[1],
                    "total": parts[2],
                    "online": parts[3],
                })

    return data


__all__ = [
    "cpu_info",
    "memory_info",
    "pci_devices",
]
