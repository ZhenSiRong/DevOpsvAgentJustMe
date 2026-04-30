"""DAG 执行记录持久化 —— SQLite 存储

表结构：
- dag_runs: 每次 DAG 执行的根记录（run_id, session_id, status, 统计等）
- dag_nodes: 每个节点的执行详情（node_id, status, result, error 等）
"""

from __future__ import annotations

import json
import logging

from .connection import db_manager, fetchall_as_dicts

logger = logging.getLogger(__name__)

# ============================================================
#  表创建（通过 db_manager.init_tables 统一执行）
# ============================================================

DAG_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS dag_runs (
    run_id              TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'pending',
    total_nodes         INTEGER NOT NULL DEFAULT 0,
    success_count       INTEGER NOT NULL DEFAULT 0,
    failed_count        INTEGER NOT NULL DEFAULT 0,
    total_execution_ms  REAL NOT NULL DEFAULT 0.0,
    rollback_commands   TEXT NOT NULL DEFAULT '[]',
    node_results        TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dag_nodes (
    run_id          TEXT NOT NULL REFERENCES dag_runs(run_id) ON DELETE CASCADE,
    node_id         TEXT NOT NULL,
    tool_name       TEXT NOT NULL DEFAULT '',
    tool_type       TEXT NOT NULL DEFAULT 'UNKNOWN',
    status          TEXT NOT NULL DEFAULT 'pending',
    result          TEXT NOT NULL DEFAULT '{}',
    error           TEXT,
    execution_ms    REAL NOT NULL DEFAULT 0.0,
    layer           INTEGER NOT NULL DEFAULT 0,
    deps            TEXT NOT NULL DEFAULT '[]',
    rollback_cmd    TEXT,
    PRIMARY KEY (run_id, node_id)
);
CREATE INDEX IF NOT EXISTS idx_dag_runs_session ON dag_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_dag_nodes_run ON dag_nodes(run_id);
"""


async def init_dag_tables() -> None:
    """建表（幂等）"""
    db = await db_manager.get_db()
    await db.executescript(DAG_TABLES_SQL)
    await db.commit()
    logger.info("DAG 表初始化完成: dag_runs + dag_nodes")


# ============================================================
#  DAG Run CRUD
# ============================================================

async def save_dag_run(record: dict) -> None:
    """保存 DAG 执行记录（含节点详情）。"""
    db = await db_manager.get_db()

    # 保存根记录
    await db.execute(
        """INSERT OR REPLACE INTO dag_runs
           (run_id, session_id, status, total_nodes, success_count,
            failed_count, total_execution_ms, rollback_commands, node_results)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record.get("run_id", ""),
            record.get("session_id", ""),
            record.get("status", "pending"),
            record.get("total_nodes", 0),
            record.get("success_count", 0),
            record.get("failed_count", 0),
            record.get("total_execution_ms", 0.0),
            json.dumps(record.get("rollback_commands", []), ensure_ascii=False),
            json.dumps(record.get("node_results", {}), ensure_ascii=False),
        ),
    )

    # 保存节点详情
    nodes = record.get("nodes", [])
    for node in nodes:
        await db.execute(
            """INSERT OR REPLACE INTO dag_nodes
               (run_id, node_id, tool_name, tool_type, status, result,
                error, execution_ms, layer, deps, rollback_cmd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("run_id", ""),
                node.get("id", ""),
                node.get("tool_name", ""),
                node.get("tool_type", "UNKNOWN"),
                node.get("status", "pending"),
                json.dumps(node.get("result", {}), ensure_ascii=False),
                node.get("error"),
                node.get("execution_ms", 0.0),
                node.get("layer", 0),
                json.dumps(node.get("deps", []), ensure_ascii=False),
                node.get("rollback_cmd"),
            ),
        )

    await db.commit()
    logger.info("DAG 执行记录已落库: run_id=%s nodes=%d", record.get("run_id"), len(nodes))


async def list_dag_runs() -> list[dict]:
    """列出所有 DAG 执行记录摘要（按时间倒序）。"""
    db = await db_manager.get_db()
    rows = await fetchall_as_dicts(
        db,
        """SELECT run_id, session_id, status, total_nodes, success_count,
                  failed_count, total_execution_ms, created_at
           FROM dag_runs
           ORDER BY created_at DESC
           LIMIT 100"""
    )
    return rows


async def get_dag_run(run_id: str) -> dict | None:
    """获取指定 DAG 执行记录（含节点详情）。"""
    db = await db_manager.get_db()

    # 查询根记录
    root_rows = await fetchall_as_dicts(
        db,
        "SELECT * FROM dag_runs WHERE run_id = ?",
        (run_id,),
    )
    if not root_rows:
        return None

    record = root_rows[0]

    # 反序列化 JSON 字段
    for field in ("rollback_commands", "node_results"):
        raw = record.get(field, "[]")
        if isinstance(raw, str):
            try:
                record[field] = json.loads(raw)
            except json.JSONDecodeError:
                record[field] = [] if field == "rollback_commands" else {}

    # 查询节点详情
    node_rows = await fetchall_as_dicts(
        db,
        """SELECT node_id, tool_name, tool_type, status, result,
                  error, execution_ms, layer, deps, rollback_cmd
           FROM dag_nodes
           WHERE run_id = ?
           ORDER BY layer, node_id""",
        (run_id,),
    )

    nodes = []
    for nr in node_rows:
        node = {
            "id": nr["node_id"],
            "tool_name": nr["tool_name"],
            "tool_type": nr["tool_type"],
            "status": nr["status"],
            "result": _parse_json(nr.get("result", "{}")),
            "error": nr["error"],
            "execution_ms": nr["execution_ms"],
            "layer": nr["layer"],
            "deps": _parse_json(nr.get("deps", "[]")),
            "rollback_cmd": nr["rollback_cmd"],
        }
        nodes.append(node)

    record["nodes"] = nodes
    return record


def _parse_json(raw) -> any:
    """安全解析 JSON，失败返回原值"""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
    return raw


__all__ = [
    "init_dag_tables",
    "save_dag_run",
    "list_dag_runs",
    "get_dag_run",
]
