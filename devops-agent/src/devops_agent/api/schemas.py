"""
API 层通用数据模型 — 统一响应格式 + 请求/响应 Schema

设计原则：
1. 所有接口使用统一的 {code, data, message} 包装
2. 分页响应使用 PaginatedResponse 通用结构
3. 错误响应使用 APIError 标准格式
4. Pydantic v2 序列化，自动生成 OpenAPI schema
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field


# ============================================================
#  通用响应包装
# ============================================================

class APIResponse(BaseModel):
    """标准成功响应：{code: 0, data: ..., message: "ok"}"""
    code: int = Field(default=0, description="业务状态码，0 表示成功")
    data: Any | None = Field(default=None, description="响应数据")
    message: str = Field(default="ok", description="人类可读的状态说明")


class APIError(BaseModel):
    """标准错误响应"""
    code: int = Field(description="错误码，非零值")
    message: str = Field(description="错误描述")
    detail: str | None = Field(default=None, description="详细错误信息（仅 debug 模式）")


# ============================================================
#  分页
# ============================================================

T = TypeVar("T")


class PaginatedData(BaseModel, Generic[T]):
    """分页数据容器"""
    items: list[T] = Field(default_factory=list, description="当前页数据")
    total: int = Field(default=0, description="总数")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页大小")
    total_pages: int = Field(default=0, description="总页数")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应包装"""
    code: int = 0
    data: PaginatedData[T]
    message: str = "ok"


# ============================================================
#  健康检查
# ============================================================

class HealthStatus(BaseModel):
    """健康检查响应"""
    status: str = Field(description="服务状态: ok | degraded | down")
    app: str = Field(description="应用名称")
    version: str = Field(description="应用版本")
    db_connected: bool = Field(description="数据库连接是否正常")
    uptime_seconds: float | None = Field(default=None, description="运行时长(秒)")


# ============================================================
#  探针请求/响应
# ============================================================

class DiskProbeRequest(BaseModel):
    """磁盘探针请求参数"""
    path: str = Field(default="/", description="目标路径，默认根分区")
    large_file_limit: int = Field(
        default=10, ge=1, le=100,
        description="大文件返回数量上限",
    )


class ProcessProbeRequest(BaseModel):
    """进程探针请求参数"""
    filter_by_name: str | None = Field(default=None, description="按进程名过滤")
    limit: int = Field(default=50, ge=1, le=500, description="返回数量上限")


class NetworkProbeRequest(BaseModel):
    """网络探针请求参数"""
    protocol: str | None = Field(
        default=None,
        description="协议过滤: tcp | udp | all",
    )
    hostname: str | None = Field(default=None, description="DNS 解析目标")


class LogProbeRequest(BaseModel):
    """日志探针请求参数"""
    since: str | None = Field(default=None, description="起始时间 (e.g. '1 hour ago')")
    until: str | None = Field(default=None, description="结束时间")
    unit: str = Field(default="system", description="日志单元: system | kernel | user")
    grep: str | None = Field(default=None, description="关键词过滤")
    lines: int = Field(default=100, ge=1, le=10000, description="最大行数")
    tail_path: str | None = Field(default=None, description="tail 文件路径（替代 journalctl）")


# ============================================================
#  执行请求/响应
# ============================================================

class ExecuteRequest(BaseModel):
    """命令执行请求"""
    command: str = Field(..., min_length=1, max_length=2000, description="要执行的 shell 命令")
    timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="超时时间(秒)")
    dry_run: bool = Field(default=False, description="试运行模式（只校验不执行）")
    session_id: str | None = Field(default=None, description="关联的会话 ID（可选，用于审计追踪）")


class ExecuteResponse(BaseModel):
    """命令执行响应"""
    command: str = ""
    status: str = ""          # SUCCESS / FAILED / TIMEOUT / REJECTED / BLOCKED
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    error_message: str | None = None
    execution_time_ms: float = 0.0
    executed_by: str = ""
    security_check: dict | None = None


# ============================================================
#  对话请求/响应
# ============================================================

class ChatMessage(BaseModel):
    """单条对话消息"""
    role: str = Field(..., description="角色: user | assistant | system")
    content: str = Field(..., min_length=1, description="消息内容")
    tool_calls: list[dict] | None = Field(default=None, description="工具调用记录")
    tool_result: Any | None = Field(default=None, description="工具执行结果")
    reasoning_events: list[dict] | None = Field(
        default=None,
        description="推理链路事件列表（仅 assistant 消息），格式为 [{type, payload, time}, ...]",
    )


class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., min_length=1, max_length=10000, description="用户消息")
    session_id: str | None = Field(default=None, description="会话 ID（空则新建）")
    stream: bool = Field(default=False, description="是否使用 SSE 流式输出")
    context: dict[str, Any] | None = Field(default=None, description="附加上下文")


class RetryRequest(BaseModel):
    """回复重试请求"""
    session_id: str = Field(..., description="会话 ID")
    message_id: str | None = Field(default=None, description="原助手消息 ID（可选，用于定位重试目标）")
    round_number: int | None = Field(default=None, description="原消息轮次号")


class ChatResponse(BaseModel):
    """对话响应"""
    session_id: str = ""
    reply: str = ""
    role: str = "assistant"
    tool_calls: list[dict] | None = None
    created_at: str = ""   # ISO 8601


# ============================================================
#  会话查询
# ============================================================

class SessionSummary(BaseModel):
    """会话摘要列表项"""
    session_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0
    title: str | None = None      # 自动从首条消息提取
    status: str = "active"        # active | archived


class SessionDetail(BaseModel):
    """会话详情"""
    session_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    messages: list[ChatMessage] = []
    execution_count: int = 0
    probe_call_count: int = 0


# ============================================================
#  审计日志
# ============================================================

class AuditLogItem(BaseModel):
    """审计日志条目"""
    id: int = 0
    timestamp: str = ""
    command: str = ""
    status: str = ""              # SUCCESS / FAILED / TIMEOUT / REJECTED / BLOCKED
    executed_by: str = ""
    execution_time_ms: float = 0.0
    exit_code: int = 0
    security_result: str | None = None
    source_ip: str | None = None


class AuditQueryParams(BaseModel):
    """审计查询参数"""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: str | None = Field(None, description="按执行状态过滤")
    start_time: str | None = Field(None, description="起始时间 ISO 8601")
    end_time: str | None = Field(None, description="结束时间 ISO 8601")
    executed_by: str | None = Field(None, description="按执行用户过滤")


__all__ = [
    # 通用
    "APIResponse", "APIError", "PaginatedData", "PaginatedResponse",
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
