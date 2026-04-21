"""API 路由层 — FastAPI 端点 + Schema 定义 + 路由注册"""

from .schemas import (
    APIResponse, APIError,
    PaginatedData, PaginatedResponse,
    HealthStatus,
    DiskProbeRequest, ProcessProbeRequest, NetworkProbeRequest, LogProbeRequest,
    ExecuteRequest, ExecuteResponse,
    ChatMessage, ChatRequest, ChatResponse,
    SessionSummary, SessionDetail,
    AuditLogItem, AuditQueryParams,
)

__all__ = [
    # 通用响应
    "APIResponse", "APIError",
    "PaginatedData", "PaginatedResponse",
    # 健康
    "HealthStatus",
    # 探针
    "DiskProbeRequest", "ProcessProbeRequest",
    "NetworkProbeRequest", "LogProbeRequest",
    # 执行
    "ExecuteRequest", "ExecuteResponse",
    # 对话
    "ChatMessage", "ChatRequest", "ChatResponse",
    # 会话
    "SessionSummary", "SessionDetail",
    # 审计
    "AuditLogItem", "AuditQueryParams",
]
