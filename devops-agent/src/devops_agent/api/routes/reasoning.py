"""
路由：推理链路查询 API

GET  /api/v1/reasoning/{session_id}          — 获取完整推理链路
GET  /api/v1/reasoning/{session_id}/summary   — 获取推理链路统计摘要
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ...db import get_reasoning_chain, get_reasoning_chain_summary
from ..schemas import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reasoning", tags=["推理链路"])


@router.get("/{session_id}", response_model=APIResponse, summary="获取推理链路")
async def get_reasoning(
    session_id: str,
    round_number: int | None = Query(None, description="指定只返回某轮链路"),
) -> APIResponse:
    """
    获取指定会话的五段式推理链路日志。

    返回按阶段有序排列的推理记录，包括：
    - SENSE    → 用户输入理解
    - ANALYZE  → LLM 推理过程
    - PLAN     → 工具调用决策
    - EXECUTE  → 工具执行结果
    - OUTPUT   → 最终回复生成
    """
    try:
        entries = await get_reasoning_chain(session_id, round_number=round_number)

        if not entries:
            raise HTTPException(status_code=404, detail=f"会话 {session_id} 无推理链路记录")

        return APIResponse(data={
            "session_id": session_id,
            "total_entries": len(entries),
            "chain": [e.to_dict() for e in entries],
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询推理链路异常: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/{session_id}/summary", response_model=APIResponse, summary="推理链路统计摘要")
async def get_summary(session_id: str) -> APIResponse:
    """
    获取推理链路的统计信息。

    包括总轮数、各阶段条目数、时间范围等。
    """
    try:
        summary = await get_reasoning_chain_summary(session_id)
        return APIResponse(data=summary)

    except Exception as e:
        logger.error("查询推理链路摘要异常: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")
