"""推理链路 + 探针模块的单元测试

覆盖：
1. reasoning.py Repository（CRUD + summary）
2. probe 模块基础结构验证（不执行真实命令）
3. reasoning_chains 表创建验证
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio


# ============================================================
#  fixture：复用 test_db_repos 的内存库模式
# ============================================================

@pytest_asyncio.fixture
async def repo_db(monkeypatch):
    """注入内存 DB 到 get_db()"""
    import aiosqlite
    from devops_agent.db.connection import CREATE_TABLES_SQL, DatabaseManager

    mem_db = await aiosqlite.connect(":memory:")
    await mem_db.execute("PRAGMA foreign_keys=ON")
    await mem_db.executescript(CREATE_TABLES_SQL)
    await mem_db.commit()

    original_get_db = DatabaseManager.get_db

    async def _mocked_get_db(self):
        return mem_db

    monkeypatch.setattr(DatabaseManager, "get_db", _mocked_get_db)

    from devops_agent.db import connection as conn_module
    orig_module_get_db = conn_module.get_db

    async def _module_mocked():
        return mem_db

    conn_module.get_db = _module_mocked
    # 同时 patch 模块级 get_db（reasoning 直接调用模块级函数）
    from devops_agent.db.reasoning import append_reasoning_entry as _orig_append
    from devops_agent.db import reasoning as reasoning_module

    yield mem_db

    # cleanup: restore originals
    DatabaseManager.get_db = original_get_db
    conn_module.get_db = orig_module_get_db
    await mem_db.close()


# ============================================================
#  1. reasoning_chains 表创建测试
# ============================================================

class TestReasoningTable:
    """验证 reasoning_chains 表正确创建"""

    @pytest.mark.asyncio
    async def test_table_exists(self, repo_db):
        cursor = await repo_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reasoning_chains'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "reasoning_chains"
        await cursor.close()

    @pytest.mark.asyncio
    async def test_table_schema(self, repo_db):
        """验证表结构和约束"""
        from devops_agent.db.connection import fetchall_as_dicts

        rows = await fetchall_as_dicts(
            repo_db,
            "PRAGMA table_info(reasoning_chains)",
        )
        columns = {r["name"] for r in rows}
        expected = {"id", "session_id", "round_number", "stage", "content", "metadata", "created_at"}
        assert columns == expected

    @pytest.mark.asyncio
    async def test_stage_check_constraint(self, repo_db):
        """验证 stage 字段的 CHECK 约束只允许五段式值"""
        valid_stages = ["SENSE", "ANALYZE", "PLAN", "EXECUTE", "OUTPUT"]
        invalid_stages = ["INPUT", "UNKNOWN", "sense", "analyze"]

        for stage in valid_stages:
            await repo_db.execute(
                "INSERT INTO reasoning_chains (session_id, round_number, stage, content) VALUES (?,?,?,?)",
                ("test_sess", 1, stage, f"test {stage}"),
            )
        await repo_db.commit()

        for stage in invalid_stages:
            with pytest.raises(Exception):  # CHECK 约束失败
                await repo_db.execute(
                    "INSERT INTO reasoning_chains (session_id, round_number, stage, content) VALUES (?,?,?,?)",
                    ("test_sess", 2, stage, f"bad {stage}"),
                )
                await repo_db.commit()


# ============================================================
#  2. ReasoningEntry CRUD 测试
# ============================================================

class TestReasoningRepo:
    """推理链路 Repository 全部方法"""

    @pytest.mark.asyncio
    async def test_append_and_retrieve(self, repo_db):
        from devops_agent.db.reasoning import append_reasoning_entry, get_reasoning_chain

        entry = await append_reasoning_entry(
            session_id="sess_test",
            round_number=1,
            stage="SENSE",
            content=json.dumps({"user_input": "查看磁盘"}),
            metadata={"tokens": 10},
        )

        assert entry.id >= 1
        assert entry.session_id == "sess_test"
        assert entry.stage == "SENSE"
        assert entry.round_number == 1

        chain = await get_reasoning_chain("sess_test")
        assert len(chain) == 1
        assert chain[0].stage == "SENSE"
        assert json.loads(chain[0].content)["user_input"] == "查看磁盘"

    @pytest.mark.asyncio
    async def test_full_five_stages(self, repo_db):
        from devops_agent.db.reasoning import append_reasoning_entry, get_reasoning_chain

        stages = ["SENSE", "ANALYZE", "PLAN", "EXECUTE", "OUTPUT"]
        for i, stage in enumerate(stages):
            await append_reasoning_entry(
                session_id="sess_5stage",
                round_number=1,
                stage=stage,
                content=f"content_{stage}",
            )

        chain = await get_reasoning_chain("sess_5stage")
        assert len(chain) == 5
        actual_stages = [e.stage for e in chain]
        assert actual_stages == stages

    @pytest.mark.asyncio
    async def test_multi_round(self, repo_db):
        from devops_agent.db.reasoning import append_reasoning_entry, get_reasoning_chain

        # Round 1: SENSE + ANALYZE + OUTPUT (无工具调用)
        await append_reasoning_entry("sess_multi", 1, "SENSE", "input")
        await append_reasoning_entry("sess_multi", 1, "ANALYZE", "thinking")
        await append_reasoning_entry("sess_multi", 1, "OUTPUT", "reply")

        # Round 2: SENSE + ANALYZE + PLAN + EXECUTE + OUTPUT (有工具调用)
        await append_reasoning_entry("sess_multi", 2, "SENSE", "input2")
        await append_reasoning_entry("sess_multi", 2, "ANALYZE", "thinking2")
        await append_reasoning_entry("sess_multi", 2, "PLAN", "plan_tool")
        await append_reasoning_entry("sess_multi", 2, "EXECUTE", "result")
        await append_reasoning_entry("sess_multi", 2, "OUTPUT", "reply2")

        all_entries = await get_reasoning_chain("sess_multi")
        assert len(all_entries) == 8

        round1_only = await get_reasoning_chain("sess_multi", round_number=1)
        assert len(round1_only) == 3
        assert all(e.round_number == 1 for e in round1_only)

        round2_only = await get_reasoning_chain("sess_multi", round_number=2)
        assert len(round2_only) == 5
        assert all(e.round_number == 2 for e in round2_only)

    @pytest.mark.asyncio
    async def test_summary(self, repo_db):
        from devops_agent.db.reasoning import (
            append_reasoning_entry,
            get_reasoning_chain_summary,
        )

        # 插入两轮数据
        await append_reasoning_entry("sess_sum", 1, "SENSE", "")
        await append_reasoning_entry("sess_sum", 1, "ANALYZE", "")
        await append_reasoning_entry("sess_sum", 1, "OUTPUT", "")
        await append_reasoning_entry("sess_sum", 2, "SENSE", "")
        await append_reasoning_entry("sess_sum", 2, "PLAN", "")
        await append_reasoning_entry("sess_sum", 2, "EXECUTE", "")
        await append_reasoning_entry("sess_sum", 2, "OUTPUT", "")

        summary = await get_reasoning_chain_summary("sess_sum")
        assert summary["total_entries"] == 7
        assert summary["total_rounds"] == 2
        assert summary["stage_counts"]["SENSE"] == 2
        assert summary["stage_counts"]["ANALYZE"] == 1
        assert summary["stage_counts"]["PLAN"] == 1
        assert summary["stage_counts"]["EXECUTE"] == 1
        assert summary["stage_counts"]["OUTPUT"] == 2

    @pytest.mark.asyncio
    async def test_empty_session(self, repo_db):
        from devops_agent.db.reasoning import get_reasoning_chain, get_reasoning_chain_summary

        chain = await get_reasoning_chain("nonexistent_session")
        assert chain == []

        summary = await get_reasoning_chain_summary("nonexistent_session")
        assert summary["total_entries"] == 0
        assert summary["total_rounds"] == 0

    @pytest.mark.asyncio
    async def test_metadata_json_serialization(self, repo_db):
        from devops_agent.db.reasoning import append_reasoning_entry, get_reasoning_chain

        meta = {"tokens": 42, "elapsed_ms": 123.45, "model": "qwen-plus"}
        entry = await append_reasoning_entry(
            session_id="sess_meta",
            round_number=1,
            stage="ANALYZE",
            content="test",
            metadata=meta,
        )

        chain = await get_reasoning_chain("sess_meta")
        restored = json.loads(chain[0].metadata or "{}")
        assert restored["tokens"] == 42
        assert abs(restored["elapsed_ms"] - 123.45) < 0.01
        assert restored["model"] == "qwen-plus"


# ============================================================
#  3. Probe 基础结构验证（不执行命令，只检查接口签名和数据类型）
# ============================================================

class TestProbeStructure:
    """验证探针模块的数据类型和接口完整性"""

    def test_base_classes_exist(self):
        from devops_agent.probe.base import (
            ProbeResult, ProbeStatus,
            DiskUsageResult, ProcessInfo,
            NetworkConnection, LogEntry,
        )
        assert issubclass(ProbeStatus, str)
        assert hasattr(DiskUsageResult, "to_dict")
        assert hasattr(ProcessInfo, "to_dict")
        assert hasattr(NetworkConnection, "to_dict")
        assert hasattr(LogEntry, "to_dict")
        assert hasattr(ProbeResult, "is_success")

    def test_probe_result_fields(self):
        from devops_agent.probe.base import ProbeResult, ProbeStatus
        r = ProbeResult(
            status=ProbeStatus.SUCCESS,
            data={"key": "value"},
            probe_name="test_probe",
            execution_time_ms=12.34,
        )
        d = r.to_dict()
        assert d["status"] == "SUCCESS"
        assert d["is_success"] is True
        assert d["data"] == {"key": "value"}
        assert "captured_at" in d

    def test_all_probes_exported(self):
        from devops_agent import probe as probe_module

        exported_funcs = [
            "disk_usage", "large_files",
            "process_list", "process_detail",
            "network_connections", "network_interfaces", "dns_resolve",
            "journal_logs", "tail_file", "grep_log",
        ]
        for name in exported_funcs:
            assert hasattr(probe_module, name), f"{name} not exported from probe module"
            assert callable(getattr(probe_module, name)), f"{name} is not callable"
