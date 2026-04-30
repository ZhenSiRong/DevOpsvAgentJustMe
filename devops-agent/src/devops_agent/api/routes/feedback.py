"""人类专家反馈 API — 驱动 Agent 自演进循环

端点：
- POST /api/v1/feedback/submit  提交专家反馈（触发规则+知识+技能更新）
- GET  /api/v1/feedback/lessons  查询已学习到的经验教训
- GET  /api/v1/evolution/stats   自演进统计
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..schemas import APIResponse

router = APIRouter(prefix="/api/v1", tags=["自演进"])

logger = logging.getLogger(__name__)


class FeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="会话 ID")
    feedback: str = Field(..., min_length=1, max_length=2000, description="专家反馈内容")
    rating: int = Field(default=5, ge=1, le=10, description="评分 1-10")


@router.post("/feedback/submit", response_model=APIResponse, summary="提交人类专家反馈")
async def submit_feedback(body: FeedbackRequest) -> APIResponse:
    """
    运维专家对一次 Agent 会话提交反馈。
    
    高权重更新：知识库(importance 3x) + 记忆强化 + 规则/技能更新。
    """
    try:
        from ...agent.evolution import get_evolution_engine
        evo = get_evolution_engine()
        record = await evo.on_human_feedback(
            session_id=body.session_id,
            feedback=body.feedback,
            rating=body.rating,
        )

        return APIResponse(
            data={
                "success_score": record.success_score,
                "lessons": record.lessons,
                "needs_skill_update": record.needs_skill_update,
                "needs_rule_update": record.needs_rule_update,
            },
            message="反馈已记录，触发知识/记忆/技能/规则更新",
        )
    except Exception as e:
        logger.error("反馈处理失败: %s", e)
        raise HTTPException(status_code=500, detail=f"反馈处理失败: {e}")


@router.get("/feedback/lessons", response_model=APIResponse, summary="查询经验教训")
async def get_lessons() -> APIResponse:
    """获取自演进过程中学到的最重要的经验教训。"""
    try:
        from ...db.connection import db_manager, fetchall_as_dicts
        db = await db_manager.get_db()
        rows = await fetchall_as_dicts(
            db,
            "SELECT id, type, content, importance, created_at FROM memories WHERE type='summary' ORDER BY importance DESC LIMIT 20"
        )
        lessons = [
            {"id": r["id"], "content": r["content"], "importance": r["importance"], "created": r["created_at"]}
            for r in rows
        ]
        return APIResponse(data={"lessons": lessons, "total": len(lessons)})
    except Exception as e:
        return APIResponse(code=500, message=str(e))


@router.get("/evolution/stats", response_model=APIResponse, summary="自演进统计")
async def evolution_stats() -> APIResponse:
    """查看自演进循环的运行统计。"""
    try:
        from ...db.connection import db_manager
        db = await db_manager.get_db()
        
        cursor = await db.execute("SELECT COUNT(*) FROM memories WHERE type='summary'")
        lessons_count = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT COUNT(*) FROM memories WHERE type='fact'")
        facts_count = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT AVG(importance) FROM memories WHERE type='summary'")
        avg_importance = (await cursor.fetchone())[0] or 0
        
        return APIResponse(data={
            "lessons_learned": lessons_count,
            "facts_stored": facts_count,
            "average_lesson_importance": round(avg_importance, 2),
            "skills_directory": "skills/",
        })
    except Exception as e:
        return APIResponse(code=500, message=str(e))


__all__ = ["router"]
