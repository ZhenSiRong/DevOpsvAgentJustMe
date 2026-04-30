"""运维知识库 RAG 增强

基于 memories 表的轻量级检索增强生成：
- 语义相关性评分（关键词 TF 匹配）
- 支持事实 (fact) / 摘要 (summary) / 偏好 (preference) 类型
- 按重要性 + 相关度排序返回 Top-K

端点：
- POST /api/v1/knowledge/search    搜索知识库
- POST /api/v1/knowledge/remember  写入新记忆
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..api.schemas import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["知识库"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="搜索查询")
    top_k: int = Field(default=5, ge=1, le=20, description="返回条数")


class RememberRequest(BaseModel):
    content: str = Field(..., min_length=1, description="记忆内容")
    type: str = Field(default="fact", description="类型: fact/summary/preference/system_state")
    importance: float = Field(default=1.0, ge=0.0, le=10.0, description="重要性")


@router.post("/search", response_model=APIResponse, summary="搜索运维知识库")
async def search_knowledge(body: SearchRequest) -> APIResponse:
    """基于关键词匹配搜索 memories 表中的运维知识。"""
    from ..db.connection import db_manager, fetchall_as_dicts

    db = await db_manager.get_db()
    rows = await fetchall_as_dicts(
        db,
        "SELECT id, type, content, importance, access_count, updated_at FROM memories WHERE type != 'system_state' ORDER BY importance DESC LIMIT 200"
    )

    # 简单关键词评分：query 中的词在 content 中出现次数
    query_terms = body.query.lower().split()
    scored = []
    for row in rows:
        content_lower = row["content"].lower()
        score = sum(content_lower.count(term) for term in query_terms if term)
        if score > 0:
            scored.append({
                "id": row["id"],
                "type": row["type"],
                "content": row["content"][:500],
                "importance": row["importance"],
                "score": score * row["importance"],  # 加权
                "access_count": row.get("access_count", 0),
                "updated_at": row.get("updated_at", ""),
            })

    scored.sort(key=lambda x: -x["score"])
    results = scored[:body.top_k]

    # 更新访问计数
    for r in results:
        await db.execute("UPDATE memories SET access_count = access_count + 1 WHERE id = ?", (r["id"],))
    if results:
        await db.commit()

    return APIResponse(data={
        "results": results,
        "total_matches": len(scored),
        "query": body.query,
    })


@router.post("/remember", response_model=APIResponse, summary="写入运维知识")
async def remember_knowledge(body: RememberRequest) -> APIResponse:
    from ..db.connection import db_manager
    db = await db_manager.get_db()
    cursor = await db.execute(
        "INSERT INTO memories (type, content, importance) VALUES (?, ?, ?)",
        (body.type, body.content, body.importance),
    )
    await db.commit()
    mem_id = cursor.lastrowid
    logger.info("新记忆已存储: id=%s type=%s", mem_id, body.type)
    return APIResponse(data={"id": mem_id}, message="已记住")


@router.get("/stats", response_model=APIResponse, summary="知识库统计")
async def knowledge_stats() -> APIResponse:
    from ..db.connection import db_manager, fetchall_as_dicts
    db = await db_manager.get_db()
    rows = await fetchall_as_dicts(
        db,
        "SELECT type, COUNT(*) as count FROM memories GROUP BY type"
    )
    total = await db.execute("SELECT COUNT(*) FROM memories")
    total_count = (await total.fetchone())[0]
    return APIResponse(data={
        "total": total_count,
        "by_type": {r["type"]: r["count"] for r in rows},
    })


__all__ = ["router"]
