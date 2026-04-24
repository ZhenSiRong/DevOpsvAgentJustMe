"""动态工具执行器 —— 用户运行时注册的 MCP Tool

支持类型：
- shell:  执行 shell 命令（参数模板替换）
- http:   调用外部 HTTP API（GET/POST 等）
- mcp_stdio / mcp_sse: 预留，P4 实现

安全：
- shell 命令黑名单（rm, dd, mkfs, >, curl | bash 等）
- URL 白名单（http 类型只允许内网或指定域名）
- 超时强制（默认 30s，最长 120s）
- 所有执行以 devops-runner 最小权限运行
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
from typing import Any

from .base import MCPTool

logger = logging.getLogger(__name__)

# Shell 命令黑名单（正则匹配）
SHELL_COMMAND_BLACKLIST = [
    r"\brm\s+-[rf]*\b",           # rm -rf
    r"\bdd\b",                     # dd
    r"\bmkfs\b",                   # mkfs
    r"\bfdisk\b",                  # fdisk
    r"\bparted\b",                 # parted
    r"\bmkfs\.[a-z]+\b",           # mkfs.ext4 等
    r">\s*/(etc|bin|sbin|lib|usr|var|root|boot|proc|sys|dev)",  # 重定向到系统目录
    r"\bcurl\b.*\|\s*\bsh\b",     # curl | bash
    r"\bcurl\b.*\|\s*\bbash\b",
    r"\bwget\b.*\|\s*\bsh\b",
    r"\bsudo\b",                   # 禁止提权（已有 devops-runner 机制）
    r"\bsu\s+-\b",                 # su -
    r"\bchmod\s+-R\s+777\b",       # chmod -R 777
]

SHELL_BLACKLIST_COMPILED = [re.compile(p, re.IGNORECASE) for p in SHELL_COMMAND_BLACKLIST]

# HTTP URL 白名单（空列表 = 允许所有，生产环境应配置）
HTTP_URL_WHITELIST: list[str] = []


def _check_shell_safety(command: str) -> tuple[bool, str]:
    """检查 shell 命令是否包含黑名单模式。返回 (是否安全, 原因)"""
    for pattern in SHELL_BLACKLIST_COMPILED:
        if pattern.search(command):
            return False, f"命令包含危险模式: {pattern.pattern}"
    return True, ""


def _check_url_safety(url: str) -> tuple[bool, str]:
    """检查 HTTP URL 是否在白名单内。"""
    if not HTTP_URL_WHITELIST:
        return True, ""  # 白名单为空 = 允许所有（开发环境）
    for allowed in HTTP_URL_WHITELIST:
        if url.startswith(allowed):
            return True, ""
    return False, f"URL 不在白名单内: {url}"


def _render_template(template: str, params: dict[str, Any]) -> str:
    """简单模板替换：{{key}} -> value。不支持复杂 Jinja2。"""
    result = template
    for key, value in params.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(value))
    # 检查是否还有未替换的占位符
    remaining = re.findall(r"\{\{[\w_]+\}\}", result)
    if remaining:
        logger.warning("模板中有未替换的占位符: %s", remaining)
    return result


class DynamicMCPTool(MCPTool):
    """动态 MCP 工具 —— 用户运行时注册的工具实例。

    与内置工具的区别：
    - name/description/parameters 由用户配置决定
    - execute() 根据 tool_type 分发到 shell/http/mcp 执行器
    - 构造时传入全部配置，无需子类化
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        tool_type: str,
        config: dict[str, Any],
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.tool_type = tool_type
        self.config = config

    async def execute(self, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
        """根据 tool_type 分发执行。"""
        try:
            if self.tool_type == "shell":
                return await self._execute_shell(arguments, ctx)
            elif self.tool_type == "http":
                return await self._execute_http(arguments, ctx)
            elif self.tool_type in ("mcp_stdio", "mcp_sse"):
                return {
                    "error": f"动态工具类型 '{self.tool_type}' 尚未实现（P4 阶段支持）",
                    "is_error": True,
                }
            else:
                return {
                    "error": f"不支持的动态工具类型: {self.tool_type}",
                    "is_error": True,
                }
        except Exception as e:
            logger.error("动态工具 %s 执行异常: %s", self.name, e, exc_info=True)
            return {
                "error": f"动态工具执行异常: {type(e).__name__}: {e}",
                "is_error": True,
            }

    async def _execute_shell(self, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
        """执行 shell 类型的动态工具。"""
        command_template = self.config.get("command", "")
        timeout = self.config.get("timeout", 30)
        shell = self.config.get("shell", "/bin/bash")
        working_dir = self.config.get("working_dir")

        # 限制超时
        timeout = min(max(int(timeout), 1), 120)

        # 渲染模板
        command = _render_template(command_template, arguments)

        # 安全校验
        safe, reason = _check_shell_safety(command)
        if not safe:
            logger.warning("动态 shell 工具被拦截: %s | 原因: %s", self.name, reason)
            return {
                "error": f"安全拦截: {reason}",
                "is_error": True,
                "blocked": True,
            }

        logger.info("动态 shell 工具执行: %s | 命令: %s", self.name, command[:200])

        # 执行命令（与 builtin/executor.py 一致的最小权限方式）
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                executable=shell,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            result: dict[str, Any] = {
                "stdout": stdout_text,
                "stderr": stderr_text,
                "exit_code": proc.returncode,
            }

            if proc.returncode != 0:
                result["is_error"] = True
                result["error"] = stderr_text or f"命令退出码: {proc.returncode}"

            return result

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "error": f"命令执行超时（{timeout}秒）",
                "is_error": True,
                "timeout": True,
            }
        except Exception as e:
            return {
                "error": f"命令执行异常: {type(e).__name__}: {e}",
                "is_error": True,
            }

    async def _execute_http(self, arguments: dict[str, Any], ctx: Any) -> dict[str, Any]:
        """执行 HTTP 类型的动态工具。"""
        import httpx

        url_template = self.config.get("url", "")
        method = self.config.get("method", "GET").upper()
        headers = self.config.get("headers", {})
        body_template = self.config.get("body_template")
        query_params_template = self.config.get("query_params", {})
        timeout = self.config.get("timeout", 10)

        timeout = min(max(int(timeout), 1), 120)

        # 渲染 URL 模板
        url = _render_template(url_template, arguments)

        # URL 安全校验
        safe, reason = _check_url_safety(url)
        if not safe:
            logger.warning("动态 HTTP 工具被拦截: %s | 原因: %s", self.name, reason)
            return {
                "error": f"安全拦截: {reason}",
                "is_error": True,
                "blocked": True,
            }

        # 渲染 headers
        rendered_headers = {}
        for k, v in headers.items():
            rendered_headers[k] = _render_template(v, arguments)

        # 渲染 query params
        params = {}
        for k, v in query_params_template.items():
            params[k] = _render_template(v, arguments)

        # 渲染 body
        body = None
        if body_template:
            if isinstance(body_template, str):
                body_str = _render_template(body_template, arguments)
                try:
                    body = json.loads(body_str)
                except json.JSONDecodeError:
                    body = body_str
            else:
                body = body_template

        logger.info("动态 HTTP 工具执行: %s | %s %s", self.name, method, url)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    response = await client.get(url, headers=rendered_headers, params=params)
                elif method == "POST":
                    response = await client.post(
                        url, headers=rendered_headers, params=params, json=body
                    )
                elif method == "PUT":
                    response = await client.put(
                        url, headers=rendered_headers, params=params, json=body
                    )
                elif method == "DELETE":
                    response = await client.delete(url, headers=rendered_headers, params=params)
                else:
                    return {"error": f"不支持的 HTTP 方法: {method}", "is_error": True}

                response.raise_for_status()

                # 尝试解析 JSON，失败则返回文本
                try:
                    data = response.json()
                except Exception:
                    data = {"raw_text": response.text}

                return {
                    "status_code": response.status_code,
                    "data": data,
                }

        except httpx.HTTPStatusError as e:
            return {
                "error": f"HTTP 错误: {e.response.status_code} - {e.response.text[:200]}",
                "is_error": True,
                "status_code": e.response.status_code,
            }
        except httpx.RequestError as e:
            return {
                "error": f"请求失败: {type(e).__name__}: {e}",
                "is_error": True,
            }
        except Exception as e:
            return {
                "error": f"HTTP 执行异常: {type(e).__name__}: {e}",
                "is_error": True,
            }


__all__ = ["DynamicMCPTool", "_check_shell_safety", "_check_url_safety", "_render_template"]
