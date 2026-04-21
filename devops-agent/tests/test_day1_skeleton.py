"""
Day 1 单元测试 —— 项目骨架层验证

TDD 红绿循环：
- 先写这些测试 → 跑 pytest 看到红色失败
- 确认骨架代码能被导入和基本调用
- 验收：Day1 结束时全部绿色

覆盖范围：
1. config.py — 配置加载、默认值、环境变量覆盖
2. models.py — dataclass 序列化/反序列化
3. connection.py — 建表 SQL 幂等性、连接管理
4. main.py — FastAPI 应用创建、health check
"""

from __future__ import annotations

import pytest


# ============================================================
#  1. 配置模块测试 (config.py)
# ============================================================
class TestConfig:
    """配置加载与默认值验证"""

    def test_settings_can_be_loaded(self, settings) -> None:
        """Settings 应该能正常加载，不抛异常"""
        assert settings is not None
        assert settings.app_name == "DevOps-Agent"

    def test_settings_has_default_values(self, settings) -> None:
        """关键配置项应有合理的默认值"""
        assert settings.app_port == 8000
        assert settings.app_host == "0.0.0.0"
        assert settings.llm_protocol in ("openai", "anthropic")
        assert 0 <= settings.llm_temperature <= 2.0
        assert settings.llm_max_tokens > 0

    def test_sudo_whitelist_parsing(self, settings) -> None:
        """sudo 白名单应正确解析为列表"""
        whitelist = settings.sudo_whitelist_list
        assert isinstance(whitelist, list)
        assert len(whitelist) > 0
        # 应包含基础只读命令
        assert "ls" in whitelist
        assert "cat" in whitelist

    def test_exec_timeout_is_positive(self, settings) -> None:
        """执行超时必须是正整数"""
        assert isinstance(settings.exec_timeout, int)
        assert settings.exec_timeout > 0

    def test_probe_config_bounds(self, settings) -> None:
        """探针超时和最大轮次应有合理边界"""
        assert settings.probe_timeout > 0
        assert settings.probe_max_rounds > 0


# ============================================================
#  2. 数据模型测试 (models.py)
# ============================================================
class TestSessionModel:
    """Session dataclass 序列化/反序列化"""

    def test_session_creation(self, sample_session: dict) -> None:
        """从字典创建 Session 实例"""
        from devops_agent.db.models import Session

        s = Session(
            id=sample_session["id"],
            title=sample_session["title"],
            user_id=sample_session["user_id"],
        )
        assert s.id == "sess-test-001"
        assert s.title == "测试会话"

    def test_session_to_dict(self, sample_session: dict) -> None:
        """Session.to_dict() 应返回正确的 API 友好格式"""
        from devops_agent.db.models import Session

        s = Session(id=sample_session["id"], title=sample_session["title"])
        d = s.to_dict()
        assert "session_id" in d
        assert d["session_id"] == sample_session["id"]
        assert "message_count" in d

    def test_session_from_row(self) -> None:
        """Session.from_row() 应正确映射 sqlite3.Row 字段"""
        from devops_agent.db.models import Session
        import sqlite3

        # 模拟 sqlite3.Row：通过实际查询构造
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE t (id TEXT, title TEXT, user_id TEXT, created_at TEXT, updated_at TEXT)")
        conn.execute("INSERT INTO t VALUES (?, ?, ?, ?, ?)",
                     ("sess-test-001", "我的会话", "user-1", "2026-04-21", "2026-04-21"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM t").fetchone()
        s = Session.from_row(row)
        assert s.title == "我的会话"
        assert s.user_id == "user-1"
        conn.close()


class TestMessageModel:
    """Message dataclass 测试"""

    def test_message_creation(self, sample_message: dict) -> None:
        """消息应支持所有角色类型"""
        from devops_agent.db.models import Message

        m = Message(
            id=sample_message["id"],
            session_id=sample_message["session_id"],
            role="user",
            content=sample_message["content"],
        )
        assert m.role == "user"
        assert m.content == "帮我查看磁盘使用情况"

    def test_message_json_fields_default_empty(self) -> None:
        """tool_calls 和 audit_trail 默认应为空列表而非 None"""
        from devops_agent.db.models import Message

        m = Message(id="test", session_id="s1", role="user")
        assert m.tool_calls == []
        assert m.audit_trail == []

    def test_message_from_row_with_json(self) -> None:
        """from_row 应正确解析 JSON 字段"""
        from devops_agent.db.models import Message
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.execute("""CREATE TABLE t (
            id TEXT, session_id TEXT, role TEXT, content TEXT,
            tool_calls TEXT, audit_trail TEXT, token_count INTEGER, created_at TEXT
        )""")
        conn.execute("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-001", "sess-1", "assistant", "帮我查看磁盘",
             '{"name":"disk_usage"}', '["received","sense"]', 42, "2026-04-21"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM t").fetchone()
        m = Message.from_row(row)
        assert m.content == "帮我查看磁盘"
        # tool_calls JSON 字段存储的是 JSON 字符串，解析后可能是 dict 或 list
        assert isinstance(m.tool_calls, (dict, list))
        assert m.audit_trail == ["received", "sense"]
        conn.close()


class TestAuditLogModel:
    """AuditLog dataclass 测试"""

    def test_audit_log_creation(self, sample_audit_log: dict) -> None:
        """审计日志应包含安全校验结果"""
        from devops_agent.db.models import AuditLog

        a = AuditLog(
            id=1,
            session_id=sample_audit_log["session_id"],
            phase=sample_audit_log["phase"],
            status=sample_audit_log["status"],
            security_result=sample_audit_log["security_result"],
            blocked_reason=sample_audit_log["blocked_reason"],
        )
        assert a.security_result == "BLOCKED"
        assert a.status == "blocked"

    def test_audit_log_to_dict_includes_security_info(self) -> None:
        """to_dict() 在有安全结果时应包含 security_result 和 blocked_reason"""
        from devops_agent.db.models import AuditLog

        a = AuditLog(
            id=1,
            session_id="s1",
            phase="security_check",
            status="blocked",
            security_result="BLOCKED",
            blocked_reason="根目录删除操作",
        )
        d = a.to_dict()
        assert d["security_result"] == "BLOCKED"
        assert d["blocked_reason"] == "根目录删除操作"


# ============================================================
#  3. 数据库连接测试 (connection.py)
# ============================================================
class TestDatabaseConnection:
    """数据库建表和连接管理"""

    @pytest.mark.asyncio
    async def test_tables_created_successfully(self, db) -> None:
        """init_tables 后应创建所有 7 张表"""
        # 查询 sqlite_master 获取所有表名
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        tables = [row[0] for row in rows]

        # 验证 7 张表都存在
        expected = [
            "audit_logs",
            "configs",
            "conversation_state",
            "messages",
            "sessions",
            "scheduled_tasks",
            "task_run_logs",
        ]
        for table in expected:
            assert table in tables, f"缺少表: {table}"

    @pytest.mark.asyncio
    async def test_create_table_is_idempotent(self, db) -> None:
        """重复执行 CREATE TABLE IF NOT EXISTS 不应报错"""
        from devops_agent.db.connection import CREATE_TABLES_SQL

        # 第一次执行已在 fixture 中完成，再执行一次
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
        # 不抛异常即通过

    @pytest.mark.asyncio
    async def test_sessions_table_schema(self, db) -> None:
        """sessions 表应有正确的字段结构"""
        cursor = await db.execute("PRAGMA table_info(sessions)")
        rows = await cursor.fetchall()
        columns = {row[1] for row in rows}

        assert "id" in columns
        assert "title" in columns
        assert "user_id" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    @pytest.mark.asyncio
    async def test_messages_table_fk_to_sessions(self, db) -> None:
        """messages 表的 session_id 应有外键约束指向 sessions"""
        cursor = await db.execute("PRAGMA foreign_key_list(messages)")
        fk_rows = await cursor.fetchall()
        fks = [row for row in fk_rows]
        
        assert len(fks) >= 1
        # 找到指向 sessions 的外键
        fk_to_sessions = [f for f in fks if f[2] == "sessions"]
        assert len(fk_to_sessions) >= 1, "messages 表缺少对 sessions 的外键约束"

    @pytest.mark.asyncio
    async def test_audit_logs_table_check_constraints(self, db) -> None:
        """audit_logs 的 phase 和 status 字段应有 CHECK 约束"""
        # 插入合法数据应成功
        await db.execute(
            "INSERT INTO audit_logs (session_id, phase, status, content) VALUES (?, ?, ?, ?)",
            ("test-session", "received", "ok", "收到用户请求"),
        )
        await db.commit()

        # 插入非法 phase 值应失败
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            await db.execute(
                "INSERT INTO audit_logs (session_id, phase, status, content) VALUES (?, ?, ?, ?)",
                ("test-session", "invalid_phase", "ok", "测试"),
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_insert_and_query_session(self, db) -> None:
        """完整 CRUD：插入会话并查询出来"""
        await db.execute(
            "INSERT INTO sessions (id, title, user_id) VALUES (?, ?, ?)",
            ("sess-crud-001", "CRUD 测试", "test-user"),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM sessions WHERE id = ?", ("sess-crud-001",)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[1] == "CRUD 测试"  # title


# ============================================================
#  4. FastAPI 应用测试 (main.py)
# ============================================================
class TestFastAPIApp:
    """应用创建和 health check 端点"""

    def test_app_creation(self) -> None:
        """create_app() 应返回有效的 FastAPI 实例"""
        from devops_agent.main import create_app
        from fastapi import FastAPI

        app = create_app()
        assert isinstance(app, FastAPI)
        assert app.title == "DevOps-Agent"

    def test_health_endpoint_exists(self) -> None:
        """/health 路由应该存在且可注册"""
        from devops_agent.main import app

        routes = [r.path for r in app.routes]
        assert "/health" in routes

    def test_cors_middleware_configured(self) -> None:
        """CORS 中间件应已配置"""
        from devops_agent.main import app

        # FastAPI/Starlette 将用户中间件包装为 Middleware 对象
        # 需要检查 .cls 属性获取实际的中间件类名
        middleware_cls_names = [
            getattr(m, "cls", type(m)).__name__ for m in app.user_middleware
        ]
        assert "CORSMiddleware" in middleware_cls_names

    def test_docs_endpoints_registered(self) -> None:
        """Swagger /docs 和 /redoc 应已注册"""
        from devops_agent.main import app

        routes = [r.path for r in app.routes]
        assert "/docs" in routes
        assert "/redoc" in routes
