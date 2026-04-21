"""数据访问层 - aiosqlite 连接池 + 自动建表"""
import sqlite3
from pathlib import Path
import logging

import aiosqlite

logger = logging.getLogger(__name__)

# 项目根目录（相对于此文件向上 3 级）
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "devops_agent.db"


# ============================================================
#  建表 SQL：5 张新表 + nanoclaw-py 原有 2 表保留
# ============================================================

CREATE_TABLES_SQL = """
-- ========================================
--  1. 会话表
-- ========================================
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,           -- UUID v4 字符串
    title       TEXT NOT NULL DEFAULT '新对话',
    user_id     TEXT NOT NULL DEFAULT 'default',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ========================================
--  2. 消息表
-- ========================================
CREATE TABLE IF NOT EXISTS messages (
    id            TEXT PRIMARY KEY,         -- UUID
    session_id    TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content       TEXT NOT NULL DEFAULT '',
    tool_calls    TEXT DEFAULT '[]',         -- JSON 数组字符串
    audit_trail   TEXT DEFAULT '[]',        -- JSON 数组: ["received","sense",...]
    token_count   INTEGER,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);

-- ========================================
--  3. 审计日志表（赛题核心：五段式闭环溯源）
-- ========================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    message_id      TEXT,                    -- 可为空：探针阶段可能无 message
    phase           TEXT NOT NULL CHECK(
        phase IN ('received', 'sense', 'inference', 'security_check', 'execution', 'response_ready')
    ),
    content         TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'ok' CHECK(status IN ('ok', 'warning', 'error', 'blocked')),
    security_result TEXT,                     -- PASSED | BLOCKED | WARNING | ESCALATE
    blocked_reason  TEXT,
    raw_input       TEXT,                     -- 安全校验时记录 LLM 原始输出
    raw_output      TEXT,                     -- 记录实际执行输出
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_logs(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_phase ON audit_logs(phase);
CREATE INDEX IF NOT EXISTS idx_audit_message ON audit_logs(message_id);

-- ========================================
--  4. 全局配置键值对表
-- ========================================
CREATE TABLE IF NOT EXISTS configs (
    key         TEXT PRIMARY KEY,             -- 如 "llm.model_name", "llm.temperature"
    value       TEXT NOT NULL DEFAULT '',      -- JSON 或纯文本
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ========================================
--  5. 对话状态表（快速恢复上下文）
-- ========================================
CREATE TABLE IF NOT EXISTS conversation_state (
    session_id       TEXT PRIMARY KEY,
    last_message_id  TEXT,
    context_summary  TEXT,                   -- 长对话压缩摘要
    total_turns      INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ========================================
--  [保留] nanoclaw-py 原有 2 表
-- ========================================
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    cron_expr   TEXT NOT NULL DEFAULT '* * * * *',
    command     TEXT NOT NULL DEFAULT '',
    enabled     INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    next_run_at TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_run_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES scheduled_tasks(id),
    status      TEXT NOT NULL DEFAULT 'pending',
    output      TEXT DEFAULT '',
    error       TEXT DEFAULT '',
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_task_runs ON task_run_logs(task_id, started_at);
"""


class DatabaseManager:
    """aiosqlite 连接池管理器 — 单例模式"""

    _instance: "DatabaseManager | None" = None
    _db: aiosqlite.Connection | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def get_db(self) -> aiosqlite.Connection:
        if self._db is None or self._db.closed:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(str(DATABASE_PATH))
            # 启用外键约束
            await self._db.execute("PRAGMA foreign_keys=ON")
            # WAL 模式提升并发性能
            await self._db.execute("PRAGMA journal_mode=WAL")
            logger.info("数据库连接已建立: %s", DATABASE_PATH)
        return self._db

    async def init_tables(self) -> None:
        """执行建表 SQL（幂等，可重复调用）"""
        db = await self.get_db()
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
        logger.info("数据库表初始化完成（7 张表）")

    async def close(self) -> None:
        if self._db and not self._db.closed:
            await self._db.close()
            logger.info("数据库连接已关闭")


# 全局单例
db_manager = DatabaseManager()


async def get_db() -> aiosqlite.Connection:
    """FastAPI 依赖注入用：获取数据库连接"""
    return await db_manager.get_db()
