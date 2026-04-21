"""
API 路由层 — 统一导出和注册

7 个路由模块：
1. health   — 健康检查 + 应用信息
2. probe    — OS 探针只读接口（磁盘/进程/网络/日志）
3. execute  — 安全命令执行（校验+白名单+sudo+超时+审计）
4. chat     — LLM 对话（自然语言驱动运维）
5. sessions — 会话管理
6. audit    — 操作审计追踪
"""

from . import health, probe, execute, chat, sessions, audit

__all__ = [
    "health", "probe", "execute",
    "chat", "sessions", "audit",
]
