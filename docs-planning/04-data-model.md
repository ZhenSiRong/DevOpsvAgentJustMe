# 04 数据模型

> 基于接口契约 + 数据访问层设计，Pydantic 模型与 ORM 定义

---

## 请求模型（Request Schemas）

```python
# api/schemas/request.py
from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000,
                         description="用户输入的自然语言指令")
    session_id: Optional[UUID] = Field(None, description="会话ID，不传则新建")
    stream: bool = Field(True, description="是否流式返回")


class SessionCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class SessionUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class AuthLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
```

---

## 响应模型（Response Schemas）

```python
# api/schemas/response.py
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional


class AuditPhase(str, Enum):
    RECEIVED = "received"
    SENSE = "sense"
    INFERENCE = "inference"
    SECURITY_CHECK = "security_check"
    EXECUTION = "execution"
    RESPONSE_READY = "response_ready"


class SecurityResult(str, Enum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"
    ESCALATE = "ESCALATE"


class ToolCallResponse(BaseModel):
    name: str
    args: dict
    result: Optional[str] = None
    status: str = Field(default="pending")  # pending / success / failed / blocked


class ChatResponse(BaseModel):
    id: str = Field(..., alias="message_id")
    session_id: str
    role: str = "assistant"
    content: str
    tool_calls: list[ToolCallResponse] = []
    audit_trail: list[AuditPhase]
    duration_ms: int
    timestamp: datetime


class ProbeResponse(BaseModel):
    type: str  # disk / process / network / logs
    timestamp: datetime
    data: dict
    duration_ms: int


class AuditLogItem(BaseModel):
    id: int
    session_id: str
    phase: AuditPhase
    content: str
    status: str
    security_result: Optional[SecurityResult] = None
    blocked_reason: Optional[str] = None
    duration_ms: int
    timestamp: datetime


class AuditLogList(BaseModel):
    total: int
    items: list[AuditLogItem]


class SessionSummary(BaseModel):
    id: str = Field(alias="session_id")
    title: str
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime


class SessionDetail(BaseModel):
    id: str = Field(alias="session_id")
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list["MessageItem"] = []


class MessageItem(BaseModel):
    id: str = Field(alias="message_id")
    session_id: str
    role: str  # user / assistant / system / tool
    content: str
    tool_calls: list[ToolCallResponse] = []
    audit_trail: list[AuditPhase] = []
    timestamp: datetime


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ErrorDetail(BaseModel):
    code: str  # VALIDATION_* / AUTH_* / SECURITY_*
    message: str
    details: Optional[dict] = None
    request_id: Optional[str] = None
```

---

## 数据库 ORM 模型（SQLite 行格式）

```python
# db/models.py
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Session:
    id: str                    # UUID string
    title: str
    user_id: str               # 关联用户表
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Session":
        return cls(
            id=row["id"], title=row["title"],
            user_id=row["user_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )


@dataclass
class Message:
    id: str                    # UUID string
    session_id: str            # FK -> sessions.id
    role: str                  # user | assistant | system | tool
    content: str
    tool_calls: str            # JSON 字符串
    audit_trail: str           # JSON 数组字符串
    token_count: Optional[int] # 用于计费/上下文长度追踪
    created_at: datetime


@dataclass
class AuditLog:
    id: int                    # 自增主键
    session_id: str            # FK -> sessions.id
    message_id: Optional[str]  # FK -> messages.id (可为空，探针阶段无消息)
    phase: str                 # received | sense | inference | security_check | execution | response_ready
    content: str               # 该阶段的操作描述或结果摘要
    status: str                # ok | warning | error | blocked
    security_result: Optional[str]  # PASSED | BLOCKED | WARNING | ESCALATE
    blocked_reason: Optional[str]
    raw_input: Optional[str]   # 原始输入（安全校验时记录 LLM 原始输出）
    raw_output: Optional[str]  # 原始执行输出
    duration_ms: int
    timestamp: datetime


@dataclass
class Config:
    key: str                   # 如 "llm.model_name", "llm.temperature", "llm.api_key"
    value: str                 # JSON 或纯文本
    updated_at: datetime


@dataclass
class ConversationState:
    session_id: str            # PK
    last_message_id: Optional[str]
    context_summary: Optional[str]  # 长对话压缩后的摘要
    total_turns: int           # 轮次计数
    updated_at: datetime
```

---

## 模型间关系图

```
User ──1:N── Session ──1:N── Message
                              │
                              1:N── AuditLog (每条消息产生多条审计记录)

Config (全局键值对，无外键)

ConversationState (按 session_id 一对一)
```

---

## 关键设计决策说明

**`audit_trail` 存在两个地方。** `messages` 表里存一个 JSON 数组（`["received","sense",...,"response"]`）用于快速展示"这条消息经历了哪些阶段"；`audit_logs` 表存详细记录（每阶段一行，含内容、耗时、安全校验结果）。前者是**索引/概览**，后者是**明细/溯源**。

**`tool_calls` 用 JSON 存储。** 因为不同工具的参数结构差异很大，不适合拆成独立表。查询时用 `json_extract()` 就行。

**`AuditLog.message_id` 可为空。** 探针调用和安全校验可能发生在消息正式生成之前（Agent 内部循环），此时还没有 message_id。
