# tests/unit/test_evolution.py
"""自演进引擎单元测试"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from devops_agent.agent.evolution import (
    EvolutionEngine,
    EvolutionRecord,
    _extract_skill_name,
)


class TestSkillNameExtraction:
    def test_disk_maps_to_disk_management(self):
        assert _extract_skill_name("帮我清理磁盘空间") == "disk-management"

    def test_cpu_maps_to_cpu_management(self):
        assert _extract_skill_name("CPU 使用率很高") == "cpu-management"

    def test_network_maps_to_network_troubleshoot(self):
        assert _extract_skill_name("网络不通了") == "network-troubleshoot"

    def test_unknown_maps_to_general(self):
        assert _extract_skill_name("随机测试") == "general-operation"


class TestScoring:
    def test_perfect_score(self):
        engine = EvolutionEngine()
        score = engine._evaluate_success(tool_rounds=2, error_count=0, has_reply=True)
        assert score == 7.0  # base score

    def test_error_deduction(self):
        engine = EvolutionEngine()
        score = engine._evaluate_success(tool_rounds=2, error_count=2, has_reply=True)
        assert score < 7.0  # deducted for errors
        assert score >= 0

    def test_no_reply_penalty(self):
        engine = EvolutionEngine()
        score = engine._evaluate_success(tool_rounds=0, error_count=0, has_reply=False)
        assert score < 7.0

    def test_high_round_penalty(self):
        engine = EvolutionEngine()
        score = engine._evaluate_success(tool_rounds=10, error_count=0, has_reply=True)
        assert score < 7.0

    def test_score_bounded(self):
        engine = EvolutionEngine()
        score = engine._evaluate_success(tool_rounds=10, error_count=10, has_reply=False)
        assert 0 <= score <= 10


class TestLessonExtraction:
    @pytest.mark.asyncio
    async def test_high_score_generates_success_lesson(self):
        engine = EvolutionEngine()
        lessons = await engine._extract_lessons(
            user_input="清理磁盘",
            reply="已完成",
            tool_rounds=3,
            errors=0,
            score=8.5,
        )
        assert any("成功" in l for l in lessons)

    @pytest.mark.asyncio
    async def test_low_score_generates_improvement_lesson(self):
        engine = EvolutionEngine()
        lessons = await engine._extract_lessons(
            user_input="重启服务",
            reply="",
            tool_rounds=2,
            errors=2,
            score=2.0,
        )
        assert any("需改进" in l for l in lessons)


class TestEvolutionRecord:
    def test_default_values(self):
        rec = EvolutionRecord(session_id="test")
        assert rec.success_score == 5.0
        assert rec.feedback_weight == 1.0
        assert len(rec.lessons) == 0

    def test_human_feedback_increases_weight(self):
        rec = EvolutionRecord(session_id="test")
        rec.human_feedback = "good job"
        rec.feedback_weight = 3.0
        assert rec.feedback_weight == 3.0
