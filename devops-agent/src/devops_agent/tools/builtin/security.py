"""内置探针：安全审计（SELinux、失败登录）"""

from __future__ import annotations

from typing import Any

from ...probe import selinux_status, failed_logins
from ..base import ProbeTool
from ..registry import register_tool


class SELinuxStatusTool(ProbeTool):
    name = "selinux_status"
    description = "获取 SELinux 状态。返回模式（Enforcing/Permissive/Disabled）、策略名称、版本。"
    parameters = {"type": "object", "properties": {}}

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await selinux_status(timeout=5.0)


class FailedLoginsTool(ProbeTool):
    name = "failed_logins"
    description = "获取失败登录记录。返回暴力破解尝试记录（用户、终端、来源IP、时间）。"
    parameters = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
    }

    async def _probe(self, arguments: dict[str, Any], ctx: Any) -> Any:
        return await failed_logins(limit=arguments.get("limit", 20), timeout=5.0)


register_tool(SELinuxStatusTool())
register_tool(FailedLoginsTool())
