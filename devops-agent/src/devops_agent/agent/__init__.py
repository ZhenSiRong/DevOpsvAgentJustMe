"""Agent 核心引擎 — 推理循环 + 工具调度 + LLM 双协议适配"""

from .core import (
    AgentContext,
    get_tool_definitions,
    build_system_prompt,
    run_agent,
    dispatch_tool_call,
    save_session_history,
    load_session_history,
    clear_session,
)
from .llm_client import (
    LLMProtocol, LLMMessage, ToolDefinition, LLMResponse,
    call_llm, call_openai_chat, call_anthropic_messages,
)

__all__ = [
    # 核心
    "AgentContext", "run_agent", "dispatch_tool_call",
    # 工具
    "get_tool_definitions", "build_system_prompt",
    # 会话
    "save_session_history", "load_session_history", "clear_session",
    # LLM
    "LLMProtocol", "LLMMessage", "ToolDefinition", "LLMResponse",
    "call_llm", "call_openai_chat", "call_anthropic_messages",
]
