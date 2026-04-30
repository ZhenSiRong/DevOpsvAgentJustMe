# tests/unit/test_context_manager.py
"""上下文窗口管理器单元测试"""

import pytest
from devops_agent.agent.context_manager import (
    ContextManager,
    AnchoredSummary,
    truncate_tool_output,
)


class TestTruncateToolOutput:
    def test_short_output_unchanged(self):
        result = truncate_tool_output("hello", 2000)
        assert result == "hello"

    def test_long_output_truncated(self):
        long_text = "x" * 3000
        result = truncate_tool_output(long_text, 2000)
        assert len(result) < 3000
        assert "输出过长" in result
        assert "头尾各" in result

    def test_empty_returns_empty(self):
        assert truncate_tool_output("") == ""


class TestTokenEstimation:
    def test_estimate_empty(self):
        mgr = ContextManager()
        assert mgr.estimate_tokens("") == 0

    def test_estimate_english(self):
        mgr = ContextManager()
        # 400 chars = ~100 tokens
        assert mgr.estimate_tokens("x" * 400) == 100

    def test_estimate_chinese(self):
        mgr = ContextManager()
        # 40 Chinese chars = ~10 tokens
        assert mgr.estimate_tokens("你好世界" * 10) == 10


class TestBudgetCheck:
    def test_under_budget_no_compression(self):
        mgr = ContextManager(max_tokens=8000, threshold=0.7)
        # 少量消息不触发压缩
        from devops_agent.agent.llm_client import LLMMessage
        msgs = [LLMMessage(role="system", content="hello")]
        result = mgr.check_and_summarize(msgs, "test")
        assert result is None

    def test_over_budget_triggers(self):
        mgr = ContextManager(max_tokens=10, threshold=0.7)
        from devops_agent.agent.llm_client import LLMMessage
        msgs = [LLMMessage(role="system", content="x" * 100)]
        result = mgr.check_and_summarize(msgs, "check disk space", 3)
        assert result is not None


class TestAnchoredSummary:
    def test_empty_summary(self):
        s = AnchoredSummary()
        assert s.to_prompt_text() == ""

    def test_full_summary(self):
        s = AnchoredSummary(
            intent="检查磁盘空间",
            changes_made="- 执行了 df -h",
            decisions_taken="- 选择清理 /tmp",
            next_steps="等待用户确认",
        )
        text = s.to_prompt_text()
        assert "检查磁盘空间" in text
        assert "执行了 df" in text
        assert "清理" in text
        assert "用户确认" in text


class TestActionRecording:
    def test_record_action(self):
        mgr = ContextManager()
        mgr.record_action("执行命令: df -h")
        assert "df -h" in mgr.summary.changes_made

    def test_record_decision(self):
        mgr = ContextManager()
        mgr.record_decision("选择重启而非热修复")
        assert "重启" in mgr.summary.decisions_taken

    def test_intent_update(self):
        mgr = ContextManager()
        mgr.update_intent("排查 CPU 飙高问题")
        assert "CPU" in mgr.summary.intent

    def test_next_steps_update(self):
        mgr = ContextManager()
        mgr.update_next_steps("准备查看 top 输出")
        assert "top" in mgr.summary.next_steps


class TestCompression:
    def test_apply_compression_reduces_messages(self):
        mgr = ContextManager(max_tokens=8000)
        mgr.update_intent("test task")
        mgr.record_action("did something")
        from devops_agent.agent.llm_client import LLMMessage
        msgs = [
            LLMMessage(role="system", content="original prompt"),
            LLMMessage(role="user", content="msg1"),
            LLMMessage(role="assistant", content="reply1"),
            LLMMessage(role="user", content="msg2"),
            LLMMessage(role="assistant", content="reply2"),
            LLMMessage(role="user", content="msg3"),
            LLMMessage(role="assistant", content="reply3"),
            LLMMessage(role="user", content="msg4"),
            LLMMessage(role="assistant", content="reply4"),
        ]
        compressed = mgr.apply_compression(msgs)
        assert len(compressed) < len(msgs)
        # 第一个消息是 system
        assert compressed[0].role == "system"
        # 包含摘要内容
        assert "test task" in compressed[0].content
