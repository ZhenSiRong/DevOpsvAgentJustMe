"""
全局 pytest fixtures —— 所有测试共享的测试基础设施

提供：
1. tmp_db: 临时内存/文件数据库（每个测试隔离）
2. settings: 已加载的配置（使用 test .env）
3. client: FastAPI TestClient（用于 API 集成测试）
4. sample_session / sample_message: 预构建的数据模型实例
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio

# ============================================================
#  确保 src 在 sys.path 中（pytest.ini 已配 pythonpath=["src"]）
# ============================================================


# ----------------------------------------------------------
#  Fixture: 测试用临时目录（避免污染项目 data/ 目录）
# ------------------------------------------------ ----------
@pytest.fixture(scope="session")
def tmp_project_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    创建一个临时"项目根目录"，用于存放测试期间的数据库等文件。
    session 级别：所有测试共享同一个临时目录。
    """
    return tmp_path_factory.mktemp("devops_agent_test")


# ----------------------------------------------------------
#  Fixture: 测试用 .env 文件覆盖
# ----------------------------------------------------------
@pytest.fixture(autouse=True)
def _mock_env(monkeypatch: pytest.MonkeyPatch, tmp_project_dir: Path) -> None:
    """
    自动应用于所有测试：将环境变量指向测试临时目录。
    这确保测试不会读取真实的 .env 或写入真实 data/ 目录。
    """
    db_path = str(tmp_project_dir / "data" / "test_agent.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key-for-unit-tests")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-jwt")
    # 清除 Settings 的 lru_cache，让每次测试重新加载
    from devops_agent.config import get_settings, Settings
    get_settings.cache_clear()


# ----------------------------------------------------------
#  Fixture: 异步数据库连接（测试隔离）
# ----------------------------------------------------------
@pytest_asyncio.fixture
async def db() -> AsyncGenerator:
    """
    提供一个初始化好表结构的异步数据库连接。
    每个使用此 fixture 的测试函数获得独立的内存数据库实例（完全隔离）。
    """
    import aiosqlite

    async with aiosqlite.connect(":memory:") as db:
        await db.execute("PRAGMA foreign_keys=ON")
        # 导入建表 SQL 并执行
        from devops_agent.db.connection import CREATE_TABLES_SQL
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
        yield db


# ----------------------------------------------------------
#  Fixture: 同步 Settings 实例
# ----------------------------------------------------------
@pytest.fixture
def settings():
    """返回已加载的测试配置实例"""
    from devops_agent.config import get_settings
    return get_settings()


# ----------------------------------------------------------
#  Fixture: 预构建的 Sample 数据模型（减少各测试重复代码）
# ----------------------------------------------------------

@pytest.fixture
def sample_session() -> dict:
    """一个标准的会话数据字典"""
    return {
        "id": "sess-test-001",
        "title": "测试会话",
        "user_id": "test-user",
    }


@pytest.fixture
def sample_message(sample_session: dict) -> dict:
    """一条标准的用户消息数据字典"""
    return {
        "id": "msg-test-001",
        "session_id": sample_session["id"],
        "role": "user",
        "content": "帮我查看磁盘使用情况",
        "tool_calls": [],
        "audit_trail": ["received", "sense", "inference"],
    }


@pytest.fixture
def sample_audit_log(sample_session: dict) -> dict:
    """一条标准审计日志数据字典"""
    return {
        "session_id": sample_session["id"],
        "phase": "security_check",
        "content": 'validate_command({"cmd": "rm -rf /"})',
        "status": "blocked",
        "security_result": "BLOCKED",
        "blocked_reason": "危险路径: 根目录删除操作被禁止",
    }
