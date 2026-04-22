"""内置执行器：安全命令执行（受安全层约束）"""

from __future__ import annotations

from typing import Any

from ...safety.executor import execute
from ..base import ExecutorTool
from ..registry import register_tool


class ExecuteCommandTool(ExecutorTool):
    name = "execute_command"
    description = (
        "执行一条运维命令（受安全校验和白名单限制）。"
        "危险命令会被自动拦截。"
        "只能执行预授权的命令类型（ls/cat/grep/systemctl/df 等）。"
        "以 devops-runner 最小权限用户执行，超时 30s 自动终止。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令",
            },
            "timeout": {
                "type": "number",
                "default": 30,
                "minimum": 1,
                "maximum": 300,
            },
        },
        "required": ["command"],
    }

    async def _execute(self, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
        command = arguments["command"]
        timeout = arguments.get("timeout", 30.0)

        result = await execute(command=command, timeout=timeout)

        return {
            "status": result.status.value,
            "exit_code": result.exit_code,
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000] if result.stderr else "",
            "error": result.error_message,
            "executed_by": result.executed_by,
            "elapsed_ms": result.execution_time_ms,
        }


register_tool(ExecuteCommandTool())
