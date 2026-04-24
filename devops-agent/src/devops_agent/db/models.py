"""数据模型 - dataclass 定义（对应 7 张表）"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Session:
    id: str
    title: str
    user_id: str = "default"
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Session:
        return cls(
            id=row["id"],
            title=row["title"],
            user_id=_row_get(row, "user_id", "default"),
            created_at=_row_get(row, "created_at", ""),
            updated_at=_row_get(row, "updated_at", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "title": self.title,
            "message_count": 0,
            "last_message_at": self.updated_at or None,
            "created_at": self.created_at,
        }


@dataclass
class Message:
    id: str
    session_id: str
    role: str  # user | assistant | system | tool
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    audit_trail: list[str] = field(default_factory=list)
    token_count: Optional[int] = None
    created_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Message:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=_row_get(row, "content", ""),
            tool_calls=json.loads(_row_get(row, "tool_calls", "[]") or "[]"),
            audit_trail=json.loads(_row_get(row, "audit_trail", "[]") or "[]"),
            token_count=_row_get(row, "token_count"),
            created_at=_row_get(row, "created_at", ""),
        )


@dataclass
class AuditLog:
    id: int
    session_id: str
    message_id: Optional[str] = None
    phase: str = ""  # received | sense | inference | security_check | execution | response_ready
    content: str = ""
    status: str = "ok"  # ok | warning | error | blocked
    security_result: Optional[str] = None  # PASSED | BLOCKED | WARNING | ESCALATE
    blocked_reason: Optional[str] = None
    raw_input: Optional[str] = None
    raw_output: Optional[str] = None
    duration_ms: int = 0
    timestamp: str = ""
    command: Optional[str] = None       # 执行的命令（execution 阶段）
    exit_code: int = 0                  # 命令退出码
    executed_by: Optional[str] = None   # 执行用户（如 devops-runner）
    source_ip: Optional[str] = None     # 请求来源 IP

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AuditLog:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            message_id=_row_get(row, "message_id"),
            phase=_row_get(row, "phase", ""),
            content=_row_get(row, "content", ""),
            status=_row_get(row, "status", "ok"),
            security_result=_row_get(row, "security_result"),
            blocked_reason=_row_get(row, "blocked_reason"),
            raw_input=_row_get(row, "raw_input"),
            raw_output=_row_get(row, "raw_output"),
            duration_ms=_row_get(row, "duration_ms", 0),
            timestamp=_row_get(row, "timestamp", ""),
            command=_row_get(row, "command"),
            exit_code=_row_get(row, "exit_code", 0),
            executed_by=_row_get(row, "executed_by"),
            source_ip=_row_get(row, "source_ip"),
        )

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "session_id": self.session_id,
            "phase": self.phase,
            "content": self.content,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "command": self.command,
            "exit_code": self.exit_code,
            "executed_by": self.executed_by,
            "source_ip": self.source_ip,
        }
        if self.security_result:
            d["security_result"] = self.security_result
        if self.blocked_reason:
            d["blocked_reason"] = self.blocked_reason
        return d


@dataclass
class Config:
    key: str
    value: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Config:
        return cls(
            key=row["key"],
            value=_row_get(row, "value", ""),
            updated_at=_row_get(row, "updated_at", ""),
        )


@dataclass
class ConversationState:
    session_id: str
    last_message_id: Optional[str] = None
    context_summary: Optional[str] = None
    total_turns: int = 0
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ConversationState:
        return cls(
            session_id=row["session_id"],
            last_message_id=_row_get(row, "last_message_id"),
            context_summary=_row_get(row, "context_summary"),
            total_turns=_row_get(row, "total_turns", 0),
            updated_at=_row_get(row, "updated_at", ""),
        )


def _row_get(row: sqlite3.Row | tuple | dict, key: str, default=None):
    """兼容 tuple / sqlite3.Row / dict 三种行类型的安全字段访问。"""
    try:
        return row[key]
    except (IndexError, TypeError):
        return default


@dataclass
class Memory:
    id: int
    type: str  # fact | summary | preference | system_state
    content: str = ""
    source_session_id: Optional[str] = None
    importance: float = 1.0
    access_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Memory:
        return cls(
            id=row["id"],
            type=row["type"],
            content=_row_get(row, "content", ""),
            source_session_id=_row_get(row, "source_session_id"),
            importance=float(_row_get(row, "importance", 1.0)),
            access_count=_row_get(row, "access_count", 0),
            created_at=_row_get(row, "created_at", ""),
            updated_at=_row_get(row, "updated_at", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "source_session_id": self.source_session_id,
            "importance": self.importance,
            "access_count": self.access_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class DynamicTool:
    id: int
    name: str
    description: str
    tool_type: str  # shell | http | mcp_stdio | mcp_sse
    config: dict = field(default_factory=dict)
    schema_json: dict = field(default_factory=dict)
    is_active: bool = True
    created_by: str = "system"
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "DynamicTool":
        config_raw = _row_get(row, "config", "{}")
        schema_raw = _row_get(row, "schema_json", "{}")
        return cls(
            id=_row_get(row, "id", 0),
            name=row["name"],
            description=_row_get(row, "description", ""),
            tool_type=row["tool_type"],
            config=json.loads(config_raw) if config_raw else {},
            schema_json=json.loads(schema_raw) if schema_raw else {},
            is_active=bool(_row_get(row, "is_active", 1)),
            created_by=_row_get(row, "created_by", "system"),
            created_at=_row_get(row, "created_at", ""),
            updated_at=_row_get(row, "updated_at", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type,
            "config": self.config,
            "schema": self.schema_json,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


__all__ = [
    "Session",
    "Message",
    "AuditLog",
    "Config",
    "ConversationState",
    "Memory",
    "DynamicTool",
]
