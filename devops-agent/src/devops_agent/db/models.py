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


def _row_get(row: sqlite3.Row, key: str, default=None):
    """sqlite3.Row 不支持 .get() 方法，用此函数替代。"""
    try:
        return row[key]
    except IndexError:
        return default


__all__ = [
    "Session",
    "Message",
    "AuditLog",
    "Config",
    "ConversationState",
]
