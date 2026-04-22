"""审计日志 Repository — 追加 + 分页查询 + 统计

封装 audit_logs 表的所有数据访问操作。
审计日志为严格的 append-only，不提供修改/删除接口（合规要求）。
"""

from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

from .connection import get_db, fetchall_as_dicts
from .models import AuditLog

logger = logging.getLogger(__name__)


async def append_audit_log(
    session_id: str,
    phase: str,
    content: str = "",
    status: str = "ok",
    security_result: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    raw_input: Optional[str] = None,
    raw_output: Optional[str] = None,
    duration_ms: int = 0,
    message_id: Optional[str] = None,
    command: Optional[str] = None,
    exit_code: int = 0,
    executed_by: Optional[str] = None,
    source_ip: Optional[str] = None,
) -> AuditLog:
    """
    追加一条审计日志。

    Args:
        phase: received | sense | inference | security_check | execution | response_ready
        status: ok | warning | error | blocked
        security_result: PASSED | BLOCKED | WARNING | ESCALATE
        command: 执行的命令（execution 阶段专用）
        exit_code: 命令退出码
        executed_by: 执行用户（如 devops-runner）
        source_ip: 请求来源 IP
    """
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO audit_logs
           (session_id, message_id, phase, content, status,
            security_result, blocked_reason, raw_input, raw_output, duration_ms,
            command, exit_code, executed_by, source_ip)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id, message_id, phase, content, status,
            security_result, blocked_reason, raw_input, raw_output, duration_ms,
            command, exit_code, executed_by, source_ip,
        ),
    )
    await db.commit()

    log_id = cursor.lastrowid
    row = await fetchall_as_dicts(
        db, "SELECT * FROM audit_logs WHERE id = ?", (log_id,),
    )
    return AuditLog.from_row(row[0])


async def query_audit_logs(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[list[AuditLog], int]:
    """
    分页查询审计日志，支持多条件组合过滤。

    Returns:
        (logs, total)
    """
    db = await get_db()
    offset = (page - 1) * page_size

    conditions: list[str] = []
    params: list = []

    if status:
        conditions.append("status = ?")
        params.append(status.lower())
    if start_time:
        conditions.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        conditions.append("timestamp <= ?")
        params.append(end_time)
    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # 总数
    count_row = await fetchall_as_dicts(
        db, f"SELECT COUNT(*) as cnt FROM audit_logs {where}",
        tuple(params),
    )
    total = count_row[0]["cnt"]

    # 分页数据（按时间降序，最新的在前）
    rows = await fetchall_as_dicts(
        db, f"""SELECT * FROM audit_logs {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?""",
        (*tuple(params), page_size, offset),
    )
    logs = [AuditLog.from_row(r) for r in rows]
    return logs, total


async def get_audit_stats() -> dict:
    """
    审计统计聚合。

    Returns:
        各状态计数、成功率、拦截率、最近 N 条记录等。
    """
    db = await get_db()

    # 按状态分布
    status_rows = await fetchall_as_dicts(
        db, "SELECT status, COUNT(*) as cnt FROM audit_logs GROUP BY status"
    )
    by_status = {r["status"]: r["cnt"] for r in status_rows}

    # 总执行数
    total_row = await fetchall_as_dicts(
        db, "SELECT COUNT(*) as cnt FROM audit_logs WHERE phase IN ('execution', 'security_check')"
    )
    total_executions = total_row[0]["cnt"]

    # 最近 5 条
    recent_rows = await fetchall_as_dicts(
        db, """SELECT * FROM audit_logs
           ORDER BY timestamp DESC LIMIT 5"""
    )
    recent = [AuditLog.from_row(r).to_dict() for r in recent_rows]

    # 计算比率
    blocked = by_status.get("blocked", 0)
    success = by_status.get("ok", 0) + by_status.get("warning", 0)
    total_all = sum(by_status.values())

    return {
        "total_executions": total_executions,
        "by_status": {
            "SUCCESS": by_status.get("ok", 0),
            "FAILED": by_status.get("error", 0),
            "TIMEOUT": 0,  # 暂无 timeout 独立记录，归入 error
            "REJECTED": by_status.get("warning", 0),
            "BLOCKED": by_status.get("blocked", 0),
        },
        "recent_executions": recent,
        "blocked_rate": round(blocked / max(total_all, 1), 4),
        "success_rate": round(success / max(total_all, 1), 4),
    }


async def get_audit_logs_by_session(session_id: str) -> list[AuditLog]:
    """获取指定会话的全部审计日志（用于会话详情展示）。"""
    db = await get_db()
    rows = await fetchall_as_dicts(
        db, """SELECT * FROM audit_logs
           WHERE session_id = ?
           ORDER BY timestamp ASC""",
        (session_id,),
    )
    return [AuditLog.from_row(r) for r in rows]


__all__ = [
    "append_audit_log",
    "query_audit_logs",
    "get_audit_stats",
    "get_audit_logs_by_session",
]
