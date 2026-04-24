"""
API 路由层 — 统一导出和注册

8 个路由模块：
1. health   — 健康检查 + 应用信息
2. probe    — OS 探针只读接口（磁盘/进程/网络/日志）
3. execute  — 安全命令执行（校验+白名单+sudo+超时+审计）
4. chat     — LLM 对话（自然语言驱动运维）
5. sessions — 会话管理
6. audit    — 操作审计追踪
7. reasoning — 推理链路五段式日志
8. safety    — 安全层状态与校验
9. tools     — 动态工具管理（用户注册自定义 MCP Tool）
"""

from . import health, probe, execute, chat, sessions, audit, reasoning, safety, tools

__all__ = [
    "health", "probe", "execute",
    "chat", "sessions", "audit", "reasoning", "safety", "tools",
]
