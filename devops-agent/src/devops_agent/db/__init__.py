"""数据访问层"""
from .connection import db_manager, get_db, DatabaseManager
from .models import Session, Message, AuditLog, Config, ConversationState

# Repository 层
from .sessions import (
    create_session,
    get_session,
    update_session_title,
    list_sessions,
    delete_session,
    touch_session,
)
from .messages import (
    append_message,
    get_messages_by_session,
    get_session_messages_all,
    count_messages_by_session,
)
from .audit import (
    append_audit_log,
    query_audit_logs,
    get_audit_stats,
    get_audit_logs_by_session,
)
from .config import (
    get_config,
    set_config,
    get_all_configs,
    delete_config,
)
from .reasoning import (
    ReasoningEntry,
    append_reasoning_entry,
    get_reasoning_chain,
    get_reasoning_chain_summary,
)
from .memory_repo import (
    add_memory,
    get_memory,
    query_memories,
    increment_access_count,
    delete_memory,
    get_memory_stats,
)

__all__ = [
    # 基础设施
    "db_manager", "get_db", "DatabaseManager",
    "Session", "Message", "AuditLog", "Config", "ConversationState", "Memory",
    # Sessions Repository
    "create_session", "get_session", "update_session_title",
    "list_sessions", "delete_session", "touch_session",
    # Messages Repository
    "append_message", "get_messages_by_session",
    "get_session_messages_all", "count_messages_by_session",
    # Audit Repository
    "append_audit_log", "query_audit_logs",
    "get_audit_stats", "get_audit_logs_by_session",
    # Config Repository
    "get_config", "set_config", "get_all_configs", "delete_config",
    # Reasoning Chain Repository
    "ReasoningEntry", "append_reasoning_entry",
    "get_reasoning_chain", "get_reasoning_chain_summary",
    # Memory Repository
    "add_memory", "get_memory", "query_memories",
    "increment_access_count", "delete_memory", "get_memory_stats",
]
