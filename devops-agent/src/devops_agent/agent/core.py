"""
Agent 核心引擎 — DevOps Agent 的大脑

从 nanoclaw-py (ApeCodeAI) 的 agent.py 改造而来：
- 删除：send_message（Telegram 特有）、schedule_task/list_tasks/pause_task/resume_task/cancel_task
- 新增：内置工具定义（探针 + 执行器）→ 替代 MCP 外部工具
- 新增：安全拦截器插入推理链路
- 新增：双协议 LLM 调用（OpenAI / Anthropic）
- 保留：会话管理、消息历史、session_id 持久化

核心流程（Tool-Use Loop）：
1. 用户输入 → 构建 messages 列表
2. 调用 LLM（含系统 Prompt + 工具描述）
3. LLM 返回文本回复 或 tool_calls
4. 如果有 tool_calls：
   a. 安全拦截器检查每个调用
   b. 执行对应工具（探针/执行器）
   c. 将结果回传给 LLM
   d. 回到步骤 3，直到 LLM 返回纯文本
5. 返回最终回复
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..probe import (
    disk_usage, large_files,
    process_list, process_detail,
    network_connections, network_interfaces, dns_resolve,
    journal_logs, tail_file, grep_log,
)
from ..safety.executor import execute, is_command_allowed, ExecutionStatus
from .llm_client import (
    LLMMessage,
    ToolDefinition,
    LLMResponse,
    call_llm,
    LLMProtocol,
)

logger = logging.getLogger(__name__)

# ============================================================
#  配置常量
# ============================================================

# 最大工具调用轮次（防止无限循环）
MAX_TOOL_ROUNDS = 10

# 会话持久化文件路径
SESSION_STATE_DIR = Path("./data/sessions")


@dataclass
class AgentContext:
    """单次对话的运行时上下文"""
    session_id: str = ""
    user_id: str = "default"
    tool_round: int = 0              # 当前工具调用轮次
    execution_count: int = 0         # 命令执行次数
    probe_call_count: int = 0        # 探针调用次数
    total_llm_tokens: int = 0        # 累计 token 用量
    start_time: float = field(default_factory=time.monotonic)
    reasoning_chain: list[dict] = field(default_factory=list)  # 推理链路日志


# ============================================================
#  工具定义 — LLM 可调用的能力清单
# ============================================================

def get_tool_definitions() -> list[ToolDefinition]:
    """
    返回所有可用工具的定义列表。

    每个工具包含 name、description 和 JSON Schema parameters。
    这些信息会被注入到 system prompt 中，让 LLM 知道自己能做什么。

    工具分两大类：
    - 探针类（只读，随时可用）：磁盘/进程/网络/日志
    - 执行类（需校验，受白名单限制）：命令执行
    """
    return [
        # ===== 只读探针工具 =====
        ToolDefinition(
            name="disk_usage",
            description="查看指定路径的磁盘使用情况。返回总空间、已用、可用、使用率百分比。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "default": "/",
                        "description": "要查看的文件系统路径，默认根分区 /",
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="large_files",
            description="扫描指定目录下最大的 N 个文件。用于定位占用空间大的文件。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "default": "/",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="process_list",
            description="列出系统进程。可按进程名过滤。返回 PID、CPU%、MEM%、命令等。",
            parameters={
                "type": "object",
                "properties": {
                    "filter_str": {
                        "type": "string",
                        "default": "",
                        "description": "按进程名模糊匹配过滤，为空则返回所有进程",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 500,
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="process_detail",
            description="获取单个进程的详细信息（PID、状态、打开的文件数、线程数等）。",
            parameters={
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "目标进程的 PID",
                    },
                },
                "required": ["pid"],
            },
        ),
        ToolDefinition(
            name="network_connections",
            description="查看当前网络连接（TCP/UDP）、监听端口。用于排查网络问题。",
            parameters={
                "type": "object",
                "properties": {},
            },
        ),
        ToolDefinition(
            name="network_interfaces",
            description="查看网络接口配置信息（IP 地址、MAC、状态）。",
            parameters={
                "type": "object",
                "properties": {},
            },
        ),
        ToolDefinition(
            name="dns_resolve",
            description="DNS 解析测试，查询域名的 IP 地址。用于诊断 DNS 问题。",
            parameters={
                "type": "object",
                "properties": {
                    "hostname": {
                        "type": "string",
                        "description": "要解析的域名",
                    },
                },
                "required": ["hostname"],
            },
        ),
        ToolDefinition(
            name="query_logs",
            description="查询系统日志(journalctl)。支持时间范围和关键词过滤。",
            parameters={
                "type": "object",
                "properties": {
                    "since": {
                        "type": "string",
                        "default": "1 hour ago",
                        "description": "起始时间，如 '30 min ago', '2024-01-01'",
                    },
                    "grep": {
                        "type": "string",
                        "default": "",
                        "description": "关键词过滤",
                    },
                    "lines": {
                        "type": "integer",
                        "default": 100,
                        "minimum": 1,
                        "maximum": 10000,
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="tail_file",
            description="读取文件末尾内容。适用于查看任意日志文件的最新输出。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件绝对路径",
                    },
                    "lines": {
                        "type": "integer",
                        "default": 50,
                    },
                },
                "required": ["path"],
            },
        ),

        # ===== 安全执行工具（受校验+白名单约束） =====
        ToolDefinition(
            name="execute_command",
            description=(
                "执行一条运维命令（受安全校验和白名单限制）。"
                "危险命令会被自动拦截。"
                "只能执行预授权的命令类型（ls/cat/grep/systemctl/df 等）。"
                "以 devops-runner 最小权限用户执行，超时 30s 自动终止。"
            ),
            parameters={
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
            },
        ),
    ]


# ============================================================
#  工具执行调度
# ============================================================

async def dispatch_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    ctx: AgentContext,
) -> dict[str, Any]:
    """
    分发工具调用到对应的实现函数。

    所有工具调用都经过此函数统一调度，便于：
    - 记录调用日志
    - 统计调用次数
    - 统一错误处理格式
    """
    ctx.tool_round += 1
    logger.info("工具调用 #%d: %s(%s)", ctx.tool_round, tool_name, arguments)

    try:
        if tool_name == "disk_usage":
            ctx.probe_call_count += 1
            path = arguments.get("path", "/")
            result = await disk_usage(path=path)
            return _format_probe_result(result)

        elif tool_name == "large_files":
            ctx.probe_call_count += 1
            path = arguments.get("path", "/")
            limit = arguments.get("limit", 10)
            results = await large_files(path=path, limit=limit)
            return _format_probe_result(results, is_list=True)

        elif tool_name == "process_list":
            ctx.probe_call_count += 1
            f = arguments.get("filter_str", "")
            limit = arguments.get("limit", 50)
            results = await process_list(filter_str=f, limit=limit)
            return _format_probe_result(results, is_list=True)

        elif tool_name == "process_detail":
            ctx.probe_call_count += 1
            pid = arguments["pid"]
            result = await process_detail(pid=pid)
            return _format_probe_result(result)

        elif tool_name == "network_connections":
            ctx.probe_call_count += 1
            results = await network_connections()
            return _format_probe_result(results, is_list=True)

        elif tool_name == "network_interfaces":
            ctx.probe_call_count += 1
            results = await network_interfaces()
            return _format_probe_result(results, is_list=True)

        elif tool_name == "dns_resolve":
            ctx.probe_call_count += 1
            hostname = arguments["hostname"]
            result = await dns_resolve(hostname=hostname)
            return _format_probe_result(result)

        elif tool_name == "query_logs":
            ctx.probe_call_count += 1
            since = arguments.get("since", "1 hour ago")
            grep = arguments.get("grep", "")
            lines = arguments.get("lines", 100)
            entries = await journal_logs(since=since, grep=grep, lines=lines)
            return _format_probe_result(entries, is_list=True)

        elif tool_name == "tail_file":
            ctx.probe_call_count += 1
            path = arguments["path"]
            lines = arguments.get("lines", 50)
            entries = await tail_file(path=path, lines=lines)
            return _format_probe_result(entries, is_list=True)

        elif tool_name == "execute_command":
            ctx.execution_count += 1
            command = arguments["command"]
            timeout = arguments.get("timeout", 30.0)

            # 安全校验已在 executor 内部完成
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

        else:
            return {"error": f"未知工具: {tool_name}", "is_error": True}

    except Exception as e:
        logger.error("工具 %s 执行异常: %s", tool_name, e, exc_info=True)
        return {
            "error": f"工具执行异常: {type(e).__name__}: {e}",
            "is_error": True,
        }


def _format_probe_result(result, is_list: bool = False) -> dict:
    """将探针结果格式化为 LLM 友好的字典"""
    if is_list and hasattr(result, "__iter__"):
        items = []
        for r in result:
            items.append(r.to_dict() if hasattr(r, "to_dict") else r)
        return {"items": items, "count": len(items)}
    
    if hasattr(result, "to_dict"):
        return result.to_dict()
    
    if isinstance(result, dict):
        return result
    
    return {"raw": str(result)}


# ============================================================
#  系统提示词构建
# ============================================================

def build_system_prompt() -> str:
    """构建 Agent 的系统 Prompt——角色、能力、规则、约束"""
    tools_info = ""
    for t in get_tool_definitions():
        params_desc = ", ".join(
            f"{k}: {v.get('description', v.get('type', ''))}"
            for k, v in t.parameters.get("properties", {}).items()
        )
        tools_info += f"- **{t.name}**({params_desc}): {t.description}\n"

    return f"""你是 DevOps Agent，一个面向国产化 Linux 环境（龙芯 loongarch64 + 麒麟高级服务器版 V11）的运维智能体。

## 你的身份
你是一个专业的 Linux 运维助手，能够通过自然语言理解用户的运维需求，
然后自动调用系统工具收集信息、分析问题、执行操作。

## 你可以使用的工具

### 📊 只读探针（随时可用）
{tools_info}

### 🔧 执行命令（受安全约束）
- **execute_command(command, timeout)**: 执行运维命令
  - 受安全校验器和白名单双重保护
  - 以 devops-runner 最小权限用户运行
  - 危险命令（rm -rf /, > /etc/passwd 等）会被拦截
  - 超时 30 秒自动终止

## 工作方式
1. **先观察再行动**：用户提出需求后，先用探针了解当前系统状态
2. **分析后建议**：根据收集到的信息给出分析和建议
3. **确认后执行**：需要执行操作时，告知用户将执行什么命令
4. **报告结果**：执行完成后报告结果

## ⚠️ 安全铁律
1. 绝不删除或修改系统关键配置文件（/etc/* 关键文件）
2. 所有命令必须通过 execute_command 工具执行（禁止直接模拟 shell）
3. 不确定的操作应主动告知用户风险并请求确认
4. 不要尝试提权到 root 用户
5. 敏感信息（密码、密钥、token）在回复中脱敏处理

## 输出要求
- 使用中文回答
- 技术信息保持准确（精确数值、完整命令、确切错误信息）
- 结构化输出（关键信息用列表或表格呈现）
- 操作前给出预期影响评估"""


# ============================================================
#  核心 Agent 循环
# ============================================================

async def run_agent(
    user_input: str,
    session_id: str | None = None,
    history: list[dict] | None = None,
    stream: bool = False,
) -> tuple[str, AgentContext]:
    """
    Agent 主入口 — Tool-Use 推理循环。

    这是整个系统的核心。接收用户自然语言输入，经过多轮 LLM 推理
    和工具调用后，返回最终回复。

    流程：
    1. 构建上下文（system prompt + 历史消息 + 当前输入）
    2. 调用 LLM
    3. 如果 LLM 返回 tool_calls → 执行工具 → 将结果回传 → 回到 2
    4. 如果 LLM 返回纯文本 → 结束循环，返回回复

    Args:
        user_input: 用户的消息
        session_id: 会话 ID（None 则新建）
        history: 历史消息（从 DB 加载，用于续接对话）
        stream: 是否流式输出（预留，Day5 完善）

    Returns:
        (reply_text, agent_context): 最终回复文本和运行时上下文
    """
    settings = get_settings()

    # ---- 初始化上下文 ----
    sid = session_id or f"sess_{int(time.time() * 1000)}"
    ctx = AgentContext(session_id=sid)

    # ---- 构建 LLM 消息列表 ----
    messages = [LLMMessage(role="system", content=build_system_prompt())]

    # 注入历史消息
    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "tool":
                # 工具结果消息
                messages.append(LLMMessage(
                    role="tool",
                    content=json.dumps(content, ensure_ascii=False),
                    name=msg.get("name", ""),
                    tool_call_id=msg.get("tool_call_id", ""),
                ))
            else:
                messages.append(LLMMessage(role=role, content=content))

    # 添加当前用户输入
    messages.append(LLMMessage(role="user", content=user_input))

    # ---- Tool-Use Loop ----
    tools_defs = get_tool_definitions()

    while ctx.tool_round < MAX_TOOL_ROUNDS:
        # 调用 LLM
        response: LLMResponse = await call_llm(
            messages=messages,
            protocol=LLMProtocol(settings.llm_protocol),
            tools=tools_defs,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            fallback_base_url=settings.anthropic_base_url,
            fallback_api_key=settings.anthropic_api_key,
            fallback_model=settings.anthropic_model,
        )

        # 记录 token 用量
        ctx.total_llm_tokens += sum(response.usage.values())

        # 记录推理链路
        ctx.reasoning_chain.append({
            "round": ctx.tool_round,
            "has_tool_calls": bool(response.tool_calls),
            "finish_reason": response.finish_reason,
            "protocol": response.protocol_used,
            "tokens_used": response.usage,
        })

        # ---- 无工具调用 → 直接返回回复 ----
        if not response.tool_calls:
            elapsed = time.monotonic() - ctx.start_time
            logger.info(
                "会话 %s 完成: %d 轮工具调用, %d 次执行, %.1fs",
                sid, ctx.tool_round, ctx.execution_count, elapsed,
            )
            return response.reply_text or "（无回复）", ctx

        # ---- 有工具调用 → 逐个执行 ----
        logger.info(
            "LLM 返回 %d 个工具调用", len(response.tool_calls),
        )

        # 将 assistant 的回复（含 tool_calls）加入消息历史
        assistant_msg = LLMMessage(
            role="assistant",
            content=response.reply_text,
            tool_calls=response.tool_calls,
        )
        messages.append(assistant_msg)

        for tc in response.tool_calls:
            tool_name = tc.get("name", "")
            args = tc.get("arguments", tc.get("args", {}))
            tool_id = tc.get("id", "")

            logger.info("执行工具: %s(%s)", tool_name, args)

            # 执行工具
            tool_result = await dispatch_tool_call(tool_name, args, ctx)

            # 将工具结果加入消息历史
            messages.append(LLMMessage(
                role="tool",
                content=json.dumps(tool_result, ensure_ascii=False, default=str),
                name=tool_name,
                tool_call_id=tool_id,
            ))

    # 超过最大轮次
    logger.warning(
        "会话 %s 达到最大工具调用轮次(%d)，强制结束",
        sid, MAX_TOOL_ROUNDS,
    )
    return (
        "抱歉，本次请求涉及的操作步骤过多，已自动中止。"
        "请尝试简化您的需求或将复杂任务拆分为多个步骤。",
        ctx,
    )


# ============================================================
#  会话持久化
# ============================================================

_session_cache: dict[str, list[dict]] = {}


def save_session_history(session_id: str, messages: list[dict]) -> None:
    """保存会话消息历史到内存缓存（后续接入 DB）"""
    _session_cache[session_id] = messages


def load_session_history(session_id: str) -> list[dict] | None:
    """加载会话消息历史"""
    return _session_cache.get(session_id)


def clear_session(session_id: str) -> None:
    """清除会话"""
    _session_cache.pop(session_id, None)


__all__ = [
    "AgentContext",
    "get_tool_definitions",
    "build_system_prompt",
    "dispatch_tool_call",
    "run_agent",
    "save_session_history",
    "load_session_history",
    "clear_session",
]
