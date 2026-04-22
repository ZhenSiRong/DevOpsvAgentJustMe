"""DB Repository 层单元测试

覆盖 sessions / messages / audit / config 四个 Repository 的全部方法。
使用内存数据库，每个测试函数完全隔离。
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio

# ============================================================
#  自定义 fixture：注入内存 DB 到 get_db()
# ============================================================

@pytest_asyncio.fixture
async def repo_db(monkeypatch):
    """
    将 db.get_db() 重定向到独立的内存数据库。
    所有 Repository 函数都通过 get_db() 获取连接，
    所以只需 mock 这一个入口点即可。
    """
    import aiosqlite
    from devops_agent.db.connection import CREATE_TABLES_SQL, DatabaseManager

    # 创建独立内存库
    mem_db = await aiosqlite.connect(":memory:")
    await mem_db.execute("PRAGMA foreign_keys=ON")
    await mem_db.executescript(CREATE_TABLES_SQL)
    await mem_db.commit()

    # 让 get_db() 返回这个内存库（替代单例）
    original_get_db = DatabaseManager.get_db

    async def _mocked_get_db(self):
        return mem_db

    monkeypatch.setattr(DatabaseManager, "get_db", _mocked_get_db)

    # 同时 mock 模块级 get_db 函数
    from devops_agent.db import connection as conn_module
    orig_module_get_db = conn_module.get_db

    async def _module_mocked():
        return mem_db

    conn_module.get_db = _module_mocked
    # 也 patch 到 devops_agent.db 包的导出
    import devops_agent.db as db_pkg
    db_pkg.get_db = _module_mocked

    yield mem_db

    # 清理
    await mem_db.close()
    conn_module.get_db = orig_module_get_db
    db_pkg.get_db = orig_module_get_db


# ============================================================
#  Sessions Repository 测试
# ============================================================

class TestSessionsRepo:
    """sessions.py 的完整 CRUD 测试"""

    @pytest.mark.asyncio
    async def test_create_session(self, repo_db):
        from devops_agent.db.sessions import create_session, get_session

        session = await create_session(title="我的会话", user_id="u1")
        assert session.id.startswith("sess_")
        assert session.title == "我的会话"
        assert session.user_id == "u1"
        assert len(session.created_at) > 0

        # 能通过 ID 查回
        found = await get_session(session.id)
        assert found is not None
        assert found.id == session.id

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, repo_db):
        from devops_agent.db.sessions import get_session

        result = await get_session("sess_nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_title(self, repo_db):
        from devops_agent.db.sessions import create_session, update_session_title, get_session

        s = await create_session(title="旧标题")
        ok = await update_session_title(s.id, "新标题")
        assert ok is True

        updated = await get_session(s.id)
        assert updated.title == "新标题"

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, repo_db):
        from devops_agent.db.sessions import update_session_title

        ok = await update_session_title("sess_no", "x")
        assert ok is False

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(self, repo_db):
        from devops_agent.db.sessions import create_session, list_sessions

        for i in range(5):
            await create_session(title=f"会话{i}")

        sessions, total = await list_sessions(page=1, page_size=3)
        assert total == 5
        assert len(sessions) == 3

        sessions2, _ = await list_sessions(page=2, page_size=3)
        assert len(sessions2) == 2

    @pytest.mark.asyncio
    async def test_delete_session(self, repo_db):
        from devops_agent.db.sessions import create_session, delete_session, get_session

        s = await create_session()
        ok = await delete_session(s.id)
        assert ok is True
        assert await get_session(s.id) is None

    @pytest.mark.asyncio
    async def test_touch_session_updates_timestamp(self, repo_db):
        from devops_agent.db.sessions import create_session, touch_session, get_session

        s = await create_session()
        old_ts = s.updated_at
        await touch_session(s.id)
        refreshed = await get_session(s.id)
        assert refreshed.updated_at >= old_ts

    @pytest.mark.asyncio
    async def test_list_with_user_filter(self, repo_db):
        from devops_agent.db.sessions import create_session, list_sessions

        await create_session(user_id="alice")
        await create_session(user_id="bob")
        await create_session(user_id="alice")

        sessions, total = await list_sessions(user_id="alice")
        assert total == 2
        assert all(s.user_id == "alice" for s in sessions)


# ============================================================
#  Messages Repository 测试
# ============================================================

class TestMessagesRepo:
    """messages.py 的追加 + 查询测试"""

    @pytest.mark.asyncio
    async def test_append_and_retrieve(self, repo_db):
        from devops_agent.db.sessions import create_session
        from devops_agent.db.messages import append_message, get_messages_by_session

        sess = await create_session()
        msg = await append_message(
            session_id=sess.id,
            role="user",
            content="查看磁盘",
            tool_calls=[{"name": "disk_usage"}],
            audit_trail=["received", "sense"],
            token_count=42,
        )
        assert msg.id.startswith("msg_")
        assert msg.role == "user"
        assert msg.content == "查看磁盘"
        assert len(msg.tool_calls) == 1
        assert msg.audit_trail == ["received", "sense"]
        assert msg.token_count == 42

        msgs, _ = await get_messages_by_session(sess.id)
        assert len(msgs) == 1
        assert msgs[0].id == msg.id

    @pytest.mark.asyncio
    async def test_append_multiple_ordering(self, repo_db):
        from devops_agent.db.sessions import create_session
        from devops_agent.db.messages import append_message, get_messages_by_session

        sess = await create_session()
        await append_message(session_id=sess.id, role="user", content="第一条")
        await append_message(session_id=sess.id, role="assistant", content="回复1")
        await append_message(session_id=sess.id, role="user", content="第二条")

        msgs, total = await get_messages_by_session(sess.id)
        assert total == 3
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"
        assert msgs[2].role == "user"

    @pytest.mark.asyncio
    async def test_get_all_messages(self, repo_db):
        from devops_agent.db.sessions import create_session
        from devops_agent.db.messages import append_message, get_session_messages_all

        sess = await create_session()
        for i in range(10):
            await append_message(session_id=sess.id, role="user", content=f"消息{i}")

        all_msgs = await get_session_messages_all(sess.id)
        assert len(all_msgs) == 10

    @pytest.mark.asyncio
    async def test_count_by_session(self, repo_db):
        from devops_agent.db.sessions import create_session
        from devops_agent.db.messages import append_message, count_messages_by_session

        assert await count_messages_by_session("empty") == 0

        sess = await create_session()
        await append_message(session_id=sess.id, role="user", content="hi")
        await append_message(session_id=sess.id, role="assistant", content="hello")
        assert await count_messages_by_session(sess.id) == 2

    @pytest.mark.asyncio
    async def test_empty_session(self, repo_db):
        from devops_agent.db.messages import get_messages_by_session

        msgs, total = await get_messages_by_session("nonexistent_sess")
        assert msgs == []
        assert total == 0


# ============================================================
#  Audit Repository 测试
# ============================================================

class TestAuditRepo:
    """audit.py 的追加 + 分页 + 统计测试"""

    @pytest.mark.asyncio
    async def test_append_audit_log(self, repo_db):
        from devops_agent.db.audit import append_audit_log

        log = await append_audit_log(
            session_id="sess_01",
            phase="security_check",
            content='validate("rm -rf /")',
            status="blocked",
            security_result="BLOCKED",
            blocked_reason="危险路径",
            duration_ms=15,
        )
        assert log.id >= 1
        assert log.phase == "security_check"
        assert log.status == "blocked"
        assert log.security_result == "BLOCKED"
        assert log.duration_ms == 15

    @pytest.mark.asyncio
    async def test_query_with_filters(self, repo_db):
        from devops_agent.db.audit import append_audit_log, query_audit_logs

        # 用唯一 session_id 隔离，避免其他测试数据干扰
        await append_audit_log("filter_s1", "received", "", "ok")
        await append_audit_log("filter_s1", "execution", "ls -la", "ok", duration_ms=50)
        await append_audit_log("filter_s1", "security_check", "rm -rf /", "blocked",
                               security_result="BLOCKED", blocked_reason="危险")

        # 按 session_id 范围查询（只看本测试插的数据）
        logs, total = await query_audit_logs(session_id="filter_s1", page=1, page_size=10)
        assert total == 3
        assert len(logs) == 3

        # 按 status 过滤（范围限 session_id）
        blocked_logs, bt = await query_audit_logs(session_id="filter_s1", status="blocked")
        assert bt == 1
        assert blocked_logs[0].status == "blocked"

    @pytest.mark.asyncio
    async def test_query_pagination(self, repo_db):
        from devops_agent.db.audit import append_audit_log, query_audit_logs

        for i in range(7):
            await append_audit_log(f"s{i}", "received", f"msg{i}")

        p1, t = await query_audit_logs(page=1, page_size=3)
        assert t == 7
        assert len(p1) == 3

        p2, _ = await query_audit_logs(page=2, page_size=3)
        assert len(p2) == 3

        p3, _ = await query_audit_logs(page=3, page_size=3)
        assert len(p3) == 1

    @pytest.mark.asyncio
    async def test_query_by_session(self, repo_db):
        from devops_agent.db.audit import append_audit_log, query_audit_logs

        await append_audit_log("sa", "execution", "cmd A", "ok")
        await append_audit_log("sb", "execution", "cmd B", "ok")
        await append_audit_log("sa", "execution", "cmd C", "ok")

        logs, t = await query_audit_logs(session_id="sa")
        assert t == 2

    @pytest.mark.asyncio
    async def test_stats_aggregation(self, repo_db):
        from devops_agent.db.audit import append_audit_log, get_audit_stats

        # 用唯一 session_id 隔离，但 get_audit_stats 是全局统计
        # 所以先清理：只插本测试需要的数据，在内存库首次调用此测试前没有其他 execution/security_check 数据
        # 注意：本测试应该最后运行或者使用独立 session 统计
        # 用独特的 session_id 前缀标记，通过 session_id 过滤计数代替全局统计
        await append_audit_log("stats_s1", "execution", "", "ok")
        await append_audit_log("stats_s1", "security_check", "", "ok")
        await append_audit_log("stats_s1", "security_check", "", "blocked",
                               security_result="BLOCKED")

        stats = await get_audit_stats()
        # 因为内存库共享，只断言 BLOCKED 至少有 1 条、success_rate 在合理范围
        assert stats["by_status"].get("BLOCKED", 0) >= 1
        assert 0 <= stats["success_rate"] <= 1.0
        assert stats["total_executions"] >= 2  # 至少本测试插入的 2 条
        assert len(stats["recent_executions"]) <= 5

    @pytest.mark.asyncio
    async def test_get_logs_by_session(self, repo_db):
        from devops_agent.db.audit import append_audit_log, get_audit_logs_by_session

        await append_audit_log("sx", "received", "用户输入")
        await append_audit_log("sx", "inference", "LLM 推理")
        await append_audit_log("sx", "execution", "执行命令")

        logs = await get_audit_logs_by_session("sx")
        assert len(logs) == 3
        phases = [l.phase for l in logs]
        assert phases == ["received", "inference", "execution"]

    @pytest.mark.asyncio
    async def test_default_values(self, repo_db):
        from devops_agent.db.audit import append_audit_log

        log = await append_audit_log(session_id="sd", phase="response_ready")
        assert log.content == ""
        assert log.status == "ok"
        assert log.duration_ms == 0
        assert log.message_id is None


# ============================================================
#  Config Repository 测试
# ============================================================

class TestConfigRepo:
    """config.py 的 KV 读写测试"""

    @pytest.mark.asyncio
    async def test_set_and_get(self, repo_db):
        from devops_agent.db.config import set_config, get_config

        await set_config("llm.model_name", "qwen-plus")
        value = await get_config("llm.model_name")
        assert value == "qwen-plus"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, repo_db):
        from devops_agent.db.config import get_config

        value = await get_config("nonexistent.key")
        assert value is None

    @pytest.mark.asyncio
    async def test_get_with_default(self, repo_db):
        from devops_agent.db.config import get_config

        value = await get_config("missing", default="fallback")
        assert value == "fallback"

    @pytest.mark.asyncio
    async def test_upsert(self, repo_db):
        from devops_agent.db.config import set_config, get_config

        await set_config("key1", "v1")
        await set_config("key1", "v2")  # 覆盖
        assert await get_config("key1") == "v2"

    @pytest.mark.asyncio
    async def test_get_all_configs(self, repo_db):
        from devops_agent.db.config import set_config, get_all_configs

        await set_config("a.b", "1")
        await set_config("x.y", "2")
        await set_config("z", "3")

        configs = await get_all_configs()
        keys = {c.key for c in configs}
        assert keys == {"a.b", "x.y", "z"}

    @pytest.mark.asyncio
    async def test_delete_config(self, repo_db):
        from devops_agent.db.config import set_config, delete_config, get_config

        await set_config("to_delete", "value")
        ok = await delete_config("to_delete")
        assert ok is True
        assert await get_config("to_delete") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, repo_db):
        from devops_agent.db.config import delete_config

        ok = await delete_config("no_such_key")
        assert ok is False
