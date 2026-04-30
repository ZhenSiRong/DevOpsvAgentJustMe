"""Agent Skills 系统 — SKILL.md 渐进式披露 + 注册发现

基于 Anthropic AgentSkills 标准（2026），实现：
1. SKILL.md 解析器（YAML frontmatter + Markdown body）
2. 三层渐进式加载（L1 name+desc → L2 body → L3 references）
3. 技能注册表（扫描 skills/ 目录）
4. 与 MCP Tool 的互补区别（Skill 教怎么做，MCP 能做什么）

参考：
- https://github.com/anthropics/skills
- https://github.com/shane9coy/Agent-Skill-Architecture-Guide
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

SKILLS_DIR = Path("./skills")


@dataclass
class AgentSkill:
    """单个 Agent Skill"""
    name: str                          # 技能名称（唯一标识）
    description: str                   # 触发描述（L1：始终注入 ~24 tokens）
    body: str = ""                     # 详细指令（L2：匹配时加载）
    references: dict[str, str] = field(default_factory=dict)  # 深度参考文档（L3：引用时加载）
    source: str = ""                   # SKILL.md 文件路径

    @property
    def frontmatter_tokens(self) -> int:
        """估算 L1 注入的 token 成本"""
        return len(self.name) // 4 + len(self.description) // 4 + 8  # ~24 typical

    def to_l1_text(self) -> str:
        """L1 格式：仅 name + description（注入 system prompt 的技能清单）"""
        return f"- **{self.name}**: {self.description}"

    def to_l2_text(self) -> str:
        """L2 格式：完整 body（匹配时注入到当前请求的上下文）"""
        if not self.body:
            return ""
        return f"## 技能：{self.name}\n{self.body}"


class SkillRegistry:
    """技能注册表 — 扫描 + 管理 + 渐进式披露"""

    def __init__(self, skills_dir: Path = SKILLS_DIR) -> None:
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, AgentSkill] = {}

    def scan(self) -> int:
        """扫描 skills/ 目录，加载所有 SKILL.md"""
        if not self.skills_dir.exists():
            logger.info("Skills 目录不存在: %s (跳过)", self.skills_dir)
            return 0

        loaded = 0
        for skill_md in self.skills_dir.rglob("SKILL.md"):
            try:
                skill = self._parse_skill(skill_md)
                if skill:
                    self._skills[skill.name] = skill
                    loaded += 1
                    logger.debug("Skill 加载: %s (%s)", skill.name, skill_md)
            except Exception as e:
                logger.warning("Skill 解析失败: %s — %s", skill_md, e)

        logger.info("Skill 扫描完成: %d 个已加载", loaded)
        return loaded

    def get(self, name: str) -> AgentSkill | None:
        return self._skills.get(name)

    def list_all(self) -> list[AgentSkill]:
        return list(self._skills.values())

    def get_l1_context(self) -> str:
        """获取所有技能的 L1 上下文（注入 system prompt）"""
        if not self._skills:
            return ""

        skills_text = "\n".join(
            s.to_l1_text() for s in self._skills.values()
        )
        return (
            "\n## 可用技能（Agent Skills）\n"
            "以下技能提供专门的工作流程和知识。匹配用户意图时自动激活。\n\n"
            f"{skills_text}\n"
        )

    def match_skills(self, user_input: str, top_k: int = 3) -> list[AgentSkill]:
        """简单关键词匹配：找到与用户输入最相关的技能（返回 L2 全量文本）"""
        if not self._skills:
            return []

        input_lower = user_input.lower()
        scored = []
        for skill in self._skills.values():
            # 在 description 和 body 中匹配
            text = (skill.description + " " + skill.body).lower()
            score = sum(
                1 for word in input_lower.split()
                if word in text and len(word) > 2
            )
            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]

    @staticmethod
    def _parse_skill(path: Path) -> AgentSkill | None:
        """解析单个 SKILL.md 文件"""
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            logger.warning("SKILL.md 缺少 YAML frontmatter: %s", path)
            return None

        # 提取 YAML frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter_raw = parts[1]
        body = parts[2].strip()

        try:
            meta = yaml.safe_load(frontmatter_raw)
        except yaml.YAMLError as e:
            logger.warning("SKILL.md YAML 解析失败: %s — %s", path, e)
            return None

        if not isinstance(meta, dict):
            return None

        name = meta.get("name", path.parent.name)
        description = meta.get("description", "")

        if not description:
            logger.warning("SKILL.md 缺少 description: %s", path)
            return None

        # 扫描 references/ 目录
        references = {}
        ref_dir = path.parent / "references"
        if ref_dir.exists() and ref_dir.is_dir():
            for ref_file in ref_dir.rglob("*.md"):
                try:
                    ref_name = ref_file.stem
                    references[ref_name] = ref_file.read_text(encoding="utf-8")[:5000]
                except Exception:
                    pass

        return AgentSkill(
            name=name,
            description=description,
            body=body[:3000],  # 限制 L2 body 大小
            references=references,
            source=str(path),
        )


# 全局单例
_skill_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
        loaded = _skill_registry.scan()
        logger.info("Skill 系统已初始化: %d 个技能", loaded)
    return _skill_registry


__all__ = [
    "AgentSkill",
    "SkillRegistry",
    "get_skill_registry",
]
