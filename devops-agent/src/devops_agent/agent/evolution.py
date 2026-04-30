"""Agent 自演进循环引擎（EvolutionEngine）

打通两个闭环：

1. **Agent 试错循环**：
   Agent执行 → 结果评估 → 知识库更新(RAG) → 记忆更新 → 技能更新

2. **人类专家反馈循环**：
   人类反馈 → 知识库更新(高权重) → 技能创建/优化 → 记忆强化 → 安全规则更新

设计原则：
- 每次 Agent 会话结束后自动触发评估
- 成功经验 → 创建/强化 Skill
- 失败教训 → 记录到知识库（标注 warning）
- 人类反馈 → 最高权重，可触发规则更新
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
#  数据模型
# ============================================================

@dataclass
class EvolutionRecord:
    """一次演进记录"""
    session_id: str
    success_score: float = 5.0        # 0-10 分，分数越高越成功
    lessons: list[str] = field(default_factory=list)       # 经验教训
    actions_count: int = 0             # 执行的操作数
    errors_count: int = 0              # 错误/失败次数
    tool_rounds: int = 0               # 工具调用轮次
    needs_skill_update: bool = False   # 是否需要更新 Skill
    needs_rule_update: bool = False    # 是否需要更新规则
    human_feedback: str = ""           # 人类专家反馈（如果存在）
    feedback_weight: float = 1.0       # 反馈权重（人类=3.0, 自动=1.0）


# ============================================================
#  演进引擎
# ============================================================

class EvolutionEngine:
    """Agent 自演进引擎"""

    # 自动评估的分数阈值
    SKILL_CREATE_THRESHOLD = 8.0       # 分数 > 8 时检查是否需要创建 Skill
    LESSON_LEARN_THRESHOLD = 3.0        # 分数 < 3 时将经验标记为教训
    HUMAN_WEIGHT = 3.0                  # 人类反馈权重（3倍于自动评估）

    def __init__(self) -> None:
        self._records: dict[str, EvolutionRecord] = {}

    # ----------------------------------------------------------
    #  自动评估（Agent 试错循环）
    # ----------------------------------------------------------

    async def on_agent_complete(
        self,
        session_id: str,
        user_input: str,
        reply: str,
        tool_rounds: int = 0,
        execution_count: int = 0,
        error_count: int = 0,
    ) -> EvolutionRecord:
        """
        Agent 一次会话结束后调用。
        自动评估 → 提取经验 → 更新知识库 + 记忆
        """
        # 1. 自动评分
        score = self._evaluate_success(
            tool_rounds=tool_rounds,
            error_count=error_count,
            has_reply=bool(reply and len(reply) > 50),
        )

        # 2. 提取经验教训
        lessons = await self._extract_lessons(
            user_input=user_input,
            reply=reply[:500],
            tool_rounds=tool_rounds,
            errors=error_count,
            score=score,
        )

        # 3. 判断是否需要 Skill 更新
        needs_skill = score >= self.SKILL_CREATE_THRESHOLD

        record = EvolutionRecord(
            session_id=session_id,
            success_score=score,
            lessons=lessons,
            actions_count=execution_count,
            errors_count=error_count,
            tool_rounds=tool_rounds,
            needs_skill_update=needs_skill,
        )
        self._records[session_id] = record

        # 4. 更新知识库 (RAG)
        await self._update_knowledge(record)

        # 5. 更新长期记忆
        await self._update_memory(record, user_input, reply)

        # 6. 成功经验 → 检查是否创建 Skill
        if needs_skill:
            await self._maybe_create_skill(record, user_input, reply)

        logger.info(
            "自演进完成: session=%s score=%.1f lessons=%d skill=%s",
            session_id, score, len(lessons), needs_skill,
        )
        return record

    # ----------------------------------------------------------
    #  人类专家反馈循环
    # ----------------------------------------------------------

    async def on_human_feedback(
        self,
        session_id: str,
        feedback: str,
        rating: int = 5,  # 1-10
    ) -> EvolutionRecord:
        """
        接收人类专家反馈 → 高权重更新所有子系统。
        """
        record = self._records.get(session_id)
        if not record:
            record = EvolutionRecord(
                session_id=session_id,
                success_score=float(rating),
            )

        record.human_feedback = feedback
        record.feedback_weight = self.HUMAN_WEIGHT

        # 1. 知识库更新（高重要性）
        importance = min(10.0, rating * 1.0)
        await self._write_knowledge(
            type_="fact",
            content=f"### 运维专家反馈\n**评分**: {rating}/10\n**反馈**: {feedback}",
            importance=importance,
            source_session=session_id,
        )

        # 2. 记忆强化
        await self._reinforce_memory(session_id, feedback, rating)

        # 3. 如果反馈提到"规则"关键词，触发规则更新
        if any(kw in feedback.lower() for kw in ["规则", "rule", "不该", "应该", "禁止", "拦截"]):
            record.needs_rule_update = True
            await self._update_safety_rule(feedback, session_id)

        # 4. 如果评分 > 7，创建/优化 Skill
        if rating >= 7:
            record.needs_skill_update = True
            await self._update_or_create_skill_from_feedback(feedback, session_id, rating)

        logger.info(
            "专家反馈处理完成: session=%s rating=%d/%d rule=%s skill=%s",
            session_id, rating, 10, record.needs_rule_update, record.needs_skill_update,
        )
        return record

    # ----------------------------------------------------------
    #  私有方法
    # ----------------------------------------------------------

    def _evaluate_success(
        self,
        tool_rounds: int,
        error_count: int,
        has_reply: bool,
    ) -> float:
        """自动评分：基础分 7 分，扣分制"""
        score = 7.0
        if not has_reply:
            score -= 3.0
        if error_count > 0:
            score -= error_count * 1.5
        if tool_rounds == 0:
            score -= 1.0  # 无工具调用（可能是简单问答，不影响）
        if tool_rounds > 8:
            score -= 2.0  # 过多轮次（效率低）
        return max(0.0, min(10.0, score))

    async def _extract_lessons(
        self,
        user_input: str,
        reply: str,
        tool_rounds: int,
        errors: int,
        score: float,
    ) -> list[str]:
        """从会话中提取经验教训"""
        lessons = []

        if score >= 8.0:
            lessons.append(f"成功: 用户问「{user_input[:80]}」时，{tool_rounds}轮工具调用后成功处理")
        elif score < self.LESSON_LEARN_THRESHOLD:
            lessons.append(f"需改进: 处理「{user_input[:80]}」时遇到 {errors} 个错误")
        if errors > 0 and errors <= tool_rounds:
            lessons.append(f"教训: {errors}/{tool_rounds} 次工具调用失败，需检查参数正确性")
        if tool_rounds > 8:
            lessons.append("注意: 工具调用轮次过多，可优化 Prompt 或拆分任务")

        return lessons

    async def _update_knowledge(self, record: EvolutionRecord) -> None:
        """写入知识库（RAG memories 表）"""
        if record.lessons:
            type_ = "fact" if record.success_score >= 6.0 else "summary"
            importance = max(1.0, record.success_score)
            for lesson in record.lessons[:3]:  # 最多 3 条
                await self._write_knowledge(
                    type_=type_,
                    content=f"[Session {record.session_id[:8]}] {lesson}",
                    importance=importance,
                    source_session=record.session_id,
                )

    async def _write_knowledge(
        self,
        type_: str,
        content: str,
        importance: float,
        source_session: str = "",
    ) -> None:
        """通用知识写入"""
        try:
            from ..db.connection import db_manager
            db = await db_manager.get_db()
            await db.execute(
                """INSERT INTO memories (type, content, importance, source_session_id)
                   VALUES (?, ?, ?, ?)""",
                (type_, content, importance, source_session),
            )
            await db.commit()
        except Exception as e:
            logger.warning("知识写入失败: %s", e)

    async def _update_memory(
        self,
        record: EvolutionRecord,
        user_input: str,
        reply: str,
    ) -> None:
        """更新长期记忆"""
        try:
            from ..memory import get_memory_manager
            mm = get_memory_manager()
            await mm.extract_and_save_from_session(
                session_id=record.session_id,
                user_input=user_input,
                reply=reply,
                ctx_info={
                    "tool_rounds": record.tool_rounds,
                    "executions": record.actions_count,
                    "score": record.success_score,
                },
            )
        except Exception as e:
            logger.warning("记忆更新失败: %s", e)

    async def _maybe_create_skill(
        self,
        record: EvolutionRecord,
        user_input: str,
        reply: str,
    ) -> None:
        """成功经验 → 自动创建新 Skill"""
        try:
            # 提取技能名称（从用户输入的意图中）
            skill_name = _extract_skill_name(user_input)
            skill_path = f"./skills/{skill_name}/SKILL.md"

            import os
            if os.path.exists(skill_path):
                logger.debug("Skill 已存在: %s", skill_name)
                return

            # 生成 SKILL.md 内容
            body = f"""# {skill_name}

## 适用场景
用户输入类型："{user_input[:200]}"

## 标准流程
1. 分析用户需求
2. 调用相关探针收集信息
3. 执行必要操作
4. 汇总并报告结果

## 参考经验
- 最近一次执行成功，评分 {record.success_score}/10
- 工具调用轮次：{record.tool_rounds}
- 操作数：{record.actions_count}

## 优化建议
此 Skill 基于 Agent 成功执行的会话自动生成。
人类专家可通过反馈进一步优化此 Skill。
"""

            import yaml
            frontmatter = yaml.dump({
                "name": skill_name,
                "description": f"当用户需要 {skill_name} 相关操作时使用此技能。"
                               f"基于成功执行模式自动生成，评分 {record.success_score}/10。",
            }, allow_unicode=True)

            os.makedirs(f"./skills/{skill_name}", exist_ok=True)
            with open(skill_path, "w", encoding="utf-8") as f:
                f.write(f"---\n{frontmatter}---\n\n{body}")

            logger.info("新 Skill 已创建: %s (评分 %.1f)", skill_name, record.success_score)

            # 重新扫描 Skills
            try:
                from .skills import get_skill_registry
                get_skill_registry().scan()
            except Exception:
                pass

        except Exception as e:
            logger.warning("Skill 自动创建失败: %s", e)

    async def _reinforce_memory(
        self,
        session_id: str,
        feedback: str,
        rating: int,
    ) -> None:
        """强化与反馈相关的记忆"""
        try:
            from ..db.connection import db_manager
            db = await db_manager.get_db()
            # 提高相关记忆的重要性
            await db.execute(
                "UPDATE memories SET importance = min(importance + ?, 10.0) WHERE source_session_id = ?",
                (rating * 0.5, session_id),
            )
            await db.commit()
        except Exception:
            pass

    async def _update_safety_rule(self, feedback: str, session_id: str) -> None:
        """人类反馈 → 更新安全规则"""
        try:
            from ..db.config import set_config
            key = f"safety.rule_from_feedback.{session_id[:8]}"
            await set_config(key, feedback[:500])
            logger.info("安全规则已更新: %s", key)
        except Exception as e:
            logger.warning("安全规则更新失败: %s", e)

    async def _update_or_create_skill_from_feedback(
        self,
        feedback: str,
        session_id: str,
        rating: int,
    ) -> None:
        """人类反馈 → 创建/优化 Skill"""
        try:
            skill_name = f"expert-feedback-{session_id[:8]}"
            skill_path = f"./skills/{skill_name}/SKILL.md"

            import os
            if not os.path.exists(skill_path):
                body = f"# 专家反馈技能 (评分 {rating}/10)\n\n## 专家建议\n{feedback[:1000]}\n\n## 来源\nsession: {session_id}\n"
                import yaml
                frontmatter = yaml.dump({
                    "name": skill_name,
                    "description": f"基于运维专家反馈创建。{feedback[:100]}",
                }, allow_unicode=True)

                os.makedirs(f"./skills/{skill_name}", exist_ok=True)
                with open(skill_path, "w", encoding="utf-8") as f:
                    f.write(f"---\n{frontmatter}---\n\n{body}")

                from .skills import get_skill_registry
                get_skill_registry().scan()
                logger.info("专家反馈 Skill 已创建: %s", skill_name)
        except Exception as e:
            logger.warning("专家反馈 Skill 创建失败: %s", e)


# ============================================================
#  全局单例 + 工具函数
# ============================================================

_evolution_engine: EvolutionEngine | None = None


def get_evolution_engine() -> EvolutionEngine:
    global _evolution_engine
    if _evolution_engine is None:
        _evolution_engine = EvolutionEngine()
    return _evolution_engine


def _extract_skill_name(user_input: str) -> str:
    """从用户输入中提取技能名称（简单启发式）"""
    input_lower = user_input.lower()
    patterns = [
        ("磁盘", "disk-management"),
        ("内存", "memory-management"),
        ("cpu", "cpu-management"),
        ("网络", "network-troubleshoot"),
        ("日志", "log-analysis"),
        ("进程", "process-management"),
        ("服务", "service-management"),
        ("安全", "security-audit"),
        ("备份", "backup-restore"),
        ("监控", "monitoring-setup"),
        ("性能", "performance-tuning"),
    ]
    for keyword, name in patterns:
        if keyword in input_lower:
            return name
    return "general-operation"


__all__ = [
    "EvolutionEngine",
    "EvolutionRecord",
    "get_evolution_engine",
]
