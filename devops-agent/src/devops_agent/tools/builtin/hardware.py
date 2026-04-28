"""内置探针：硬件信息（CPU、内存、PCI设备）"""

from __future__ import annotations

from typing import Any

from ...probe import cpu_info, memory_info, pci_devices
from ..base import ProbeTool
from ..registry import register_tool


class CPUInfoTool(ProbeTool):
    name = "cpu_info"
    description = "获取 CPU 信息。返回架构、型号、厂商、核心数、频率、缓存大小。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await cpu_info(timeout=5.0)


class MemoryInfoTool(ProbeTool):
    name = "memory_info"
    description = "获取内存硬件信息。返回总容量、内存条分布、块大小。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await memory_info(timeout=5.0)


class PCIDevicesTool(ProbeTool):
    name = "pci_devices"
    description = "获取 PCI 设备列表。返回网卡、GPU、存储控制器等设备的插槽和描述。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await pci_devices(timeout=5.0)


register_tool(CPUInfoTool())
register_tool(MemoryInfoTool())
register_tool(PCIDevicesTool())
