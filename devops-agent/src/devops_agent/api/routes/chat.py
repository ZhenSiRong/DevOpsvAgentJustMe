"""
路由 4/7：LLM 对话接口 — Agent 的核心交互入口

POST /api/v1/chat           — 发送消息给 Agent（新建或续接会话）
GET  /api/v1/chat/history    — 获取对话历史

核心逻辑：
- 接收自然语言消息 → agent.run_agent() → 返回回复（含工具调用自动循环）
- 双协议支持：OpenAI Chat Completions / Anthropic Messages（MiniMax 兼容）
- 工具调用循环：LLM 决定调用探针/执行器时，自动执行并回传结果
- 会话管理：首次消息自动创建会话，后续按 session_id 续接
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from ...agent import run_agent, save_session_history, load_session_history
from ..schemas import APIResponse, ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["AI 对话"])


@router.post("/chat", response_model=APIResponse, summary="与 Agent 对话")
async def chat(body: ChatRequest) -> APIResponse:
    """
    与 DevOps Agent 对话。

    用户输入自然语言运维需求（如"看看磁盘使用率"、"重启 nginx 服务"），
    Agent 通过 LLM 理解意图后调用内置工具完成操作并返回结果。

    完整流程：
    1. 获取/创建会话，加载历史消息
    2. 调用 agent.run_agent() 进入 Tool-Use 推理循环
    3. LLM 分析意图 → 如需工具则安全拦截+执行→ 结果回传 → 循环直到返回纯文本
    4. 保存消息到会话历史
    5. 返回最终回复 + 元数据（工具轮次/token 用量/耗时）
    """
    # Step 1: 会话管理
    session_id = body.session_id or _generate_session_id()

    # Step 2: 加载历史消息（用于续接对话）
    history = None
    if body.session_id:
        history = load_session_history(body.session_id)

    # Step 3: 调用 Agent 核心循环
    try:
        start = time.monotonic()
        reply, ctx = await run_agent(
            user_input=body.message,
            session_id=session_id,
            history=history,
            stream=body.stream,
        )

        # Step 4: 保存当前交互到会话历史
        current_msg = {"role": "user", "content": body.message}
        reply_msg = {"role": "assistant", "content": reply}

        if body.session_id:
            existing = load_session_history(body.session_id) or []
            existing.extend([current_msg, reply_msg])
            save_session_history(body.session_id, existing)
        else:
            save_session_history(session_id, [current_msg, reply_msg])

        return APIResponse(
            data=ChatResponse(
                session_id=ctx.session_id,
                reply=reply,
                role="assistant",
                tool_calls=None,  # 工具调用已在内部循环中处理完毕
                created_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump(),
        )

    except Exception as e:
        logger.error("对话异常: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"LLM/Agent 异常: {type(e).__name__}: {e}")


@router.get("/chat/history", response_model=APIResponse, summary="对话历史")
async def chat_history(
    session_id: str = Query(..., description="会话 ID"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> APIResponse:
    """获取指定会话的对话历史"""
    history = load_session_history(session_id)

    if history is None:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")

    # 简单分页
    start = (page - 1) * page_size
    end = start + page_size
    paginated = history[start:end]

    return APIResponse(
        data={
            "session_id": session_id,
            "messages": paginated,
            "total_count": len(history),
            "page": page,
            "page_size": page_size,
        },
    )


# ============================================================
#  内部辅助函数
# ============================================================

def _generate_session_id() -> str:
    """生成新的会话 ID"""
    return f"sess_{uuid.uuid4().hex[:12]}"
