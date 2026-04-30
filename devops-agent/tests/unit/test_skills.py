# tests/unit/test_skills.py
"""Agent Skills 系统单元测试"""

import pytest
import tempfile
from pathlib import Path
from devops_agent.agent.skills import AgentSkill, SkillRegistry


class TestAgentSkill:
    def test_frontmatter_tokens_estimation(self):
        skill = AgentSkill(name="test", description="a test skill")
        tokens = skill.frontmatter_tokens
        assert tokens > 0

    def test_to_l1_text(self):
        skill = AgentSkill(name="test-skill", description="A test skill for testing")
        l1 = skill.to_l1_text()
        assert "test-skill" in l1
        assert "A test skill" in l1

    def test_to_l2_text_empty(self):
        skill = AgentSkill(name="test", description="desc")
        assert skill.to_l2_text() == ""

    def test_to_l2_text_with_body(self):
        skill = AgentSkill(name="test", description="desc", body="# hello")
        l2 = skill.to_l2_text()
        assert "hello" in l2
        assert "test" in l2


class TestSkillRegistry:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.skill_dir = Path(self.tmpdir) / "my-skill"
        self.skill_dir.mkdir(parents=True)
        (self.skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: "When user wants to test skills, use this."
---

# My Skill

## Steps
1. Step one
2. Step two
""", encoding="utf-8")

    def test_scan_loads_skill(self):
        reg = SkillRegistry(skills_dir=self.tmpdir)
        count = reg.scan()
        assert count == 1
        assert reg.get("my-skill") is not None

    def test_get_l1_context(self):
        reg = SkillRegistry(skills_dir=self.tmpdir)
        reg.scan()
        ctx = reg.get_l1_context()
        assert "my-skill" in ctx
        assert "test skills" in ctx

    def test_match_skills_finds_relevant(self):
        reg = SkillRegistry(skills_dir=self.tmpdir)
        reg.scan()
        matches = reg.match_skills("I want to test skills")
        assert len(matches) > 0
        assert matches[0].name == "my-skill"

    def test_match_skills_no_match(self):
        reg = SkillRegistry(skills_dir=self.tmpdir)
        reg.scan()
        matches = reg.match_skills("completely unrelated query")
        assert len(matches) == 0

    def test_missing_directory_returns_zero(self):
        reg = SkillRegistry(skills_dir="/nonexistent/path")
        assert reg.scan() == 0

    def test_list_all(self):
        reg = SkillRegistry(skills_dir=self.tmpdir)
        reg.scan()
        skills = reg.list_all()
        assert len(skills) == 1
