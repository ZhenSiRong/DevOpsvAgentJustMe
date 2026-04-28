"""内置探针：systemd 服务管理"""

from __future__ import annotations

from typing import Any

from ...probe import service_status, service_list
from ..base import ProbeTool
from ..registry import register_tool


class ServiceStatusTool(ProbeTool):
    name = "service_status"
    description = "获取单个 systemd 服务的详细状态。返回 active/inactive/failed、PID、最近日志等。"
    parameters = {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "服务名，如 nginx、sshd",
            },
        },
        "required": ["service"],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await service_status(service=arguments["service"], timeout=10.0)


class ServiceListTool(ProbeTool):
    name = "service_list"
    description = "列出 systemd 服务单元。支持按状态过滤（running/failed/active）。"
    parameters = {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "description": "状态过滤，如 running、failed、active",
            },
            "service_type": {
                "type": "string",
                "default": "service",
                "description": "单元类型",
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await service_list(
            state=arguments.get("state"),
            service_type=arguments.get("service_type", "service"),
            timeout=10.0,
        )


register_tool(ServiceStatusTool())
register_tool(ServiceListTool())
