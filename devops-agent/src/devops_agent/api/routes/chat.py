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
from fastapi.responses import StreamingResponse

from ...agent import run_agent, run_agent_stream, save_session_history, load_session_history
from ...db import get_session, create_session, append_message, touch_session, get_messages_by_session
from ..schemas import APIResponse, ChatRequest, ChatResponse, RetryRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["AI 对话"])


@router.post("/chat", response_model=APIResponse, summary="与 Agent 对话")
async def chat(body: ChatRequest) -> APIResponse:
    """
    与 DevOps Agent 对话。

    完整流程：
    1. 获取/创建会话，加载历史消息
    2. 调用 agent.run_agent() 进入 Tool-Use 推理循环
    3. 保存用户消息和助手回复到数据库
    4. 返回最终回复 + 元数据
    """
    # Step 1: 会话管理
    session_id = body.session_id or _generate_session_id()

    # 确保会话存在
    if body.session_id:
        existing = await get_session(body.session_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"会话 {body.session_id} 不存在")
    else:
        await create_session(title=_make_title(body.message), session_id=session_id)

    # Step 2: 加载历史消息（用于续接对话）
    history = None
    if body.session_id:
        history = await load_session_history(body.session_id)

    # Step 3: 先保存用户消息（无论LLM是否成功，用户消息不能丢）
    await append_message(
        session_id=session_id,
        role="user",
        content=body.message,
    )

    # Step 4: 调用 Agent 核心循环
    try:
        start = time.monotonic()
        reply, ctx = await run_agent(
            user_input=body.message,
            session_id=session_id,
            history=history,
            stream=body.stream,
        )

        # Step 5: 保存助手回复到 DB
        await append_message(
            session_id=session_id,
            role="assistant",
            content=reply,
        )

        # 更新时间戳
        await touch_session(session_id)

        return APIResponse(
            data=ChatResponse(
                session_id=ctx.session_id,
                reply=reply,
                role="assistant",
                tool_calls=None,
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
    """获取指定会话的对话历史（分页）"""
    messages, total = await get_messages_by_session(session_id, page=page, page_size=page_size)

    return APIResponse(
        data={
            "session_id": session_id,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in messages
            ],
            "total_count": total,
            "page": page,
            "page_size": page_size,
        },
    )


@router.post("/chat/stream", summary="与 Agent 对话（SSE 流式）")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    """
    与 DevOps Agent 对话 —— SSE 流式输出。

    返回 Server-Sent Events，前端可实时看到推理进度：
    - start → sense → analyze → plan → execute → execute_done → output → done

    事件格式（每行一个 SSE 事件）：
        event: analyze\n
        data: {"has_tool_calls": true, "reply_preview": "..."}\n\n
    """
    session_id = body.session_id or _generate_session_id()

    # 确保会话存在
    if body.session_id:
        existing = await get_session(body.session_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"会话 {body.session_id} 不存在")
    else:
        await create_session(title=_make_title(body.message), session_id=session_id)

    # 加载历史
    history = None
    if body.session_id:
        history = await load_session_history(body.session_id)

    async def event_generator():
        """SSE 事件生成器"""
        import json

        # 先保存用户消息（LLM失败也不能丢）
        try:
            await append_message(session_id=session_id, role="user", content=body.message)
        except Exception as db_err:
            logger.warning("流式对话保存用户消息失败: %s", db_err)

        full_reply = ""
        session_id_final = session_id

        try:
            async for event in run_agent_stream(
                user_input=body.message,
                session_id=session_id,
                history=history,
            ):
                event_type = event.get("event", "unknown")
                yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

                # 捕获最终回复用于保存到 DB
                if event_type == "output":
                    full_reply = event.get("reply", "")
                    session_id_final = event.get("session_id", session_id)

                if event_type == "done":
                    session_id_final = event.get("session_id", session_id)

        except Exception as e:
            logger.error("流式对话异常: %s", e, exc_info=True)
            error_event = {"event": "error", "detail": f"{type(e).__name__}: {e}"}
            yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return

        # 保存助手回复到 DB（流结束后异步保存，不阻塞响应）
        try:
            if full_reply:
                await append_message(session_id=session_id_final, role="assistant", content=full_reply)
            await touch_session(session_id_final)
        except Exception as db_err:
            logger.warning("流式对话后保存助手回复失败: %s", db_err)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


@router.post("/chat/retry", summary="重新生成回复（SSE 流式）")
async def chat_retry(body: RetryRequest) -> StreamingResponse:
    """
    对指定会话的最后一条用户消息重新执行 Agent 推理，生成新版本回复。

    流程：
    1. 加载会话历史消息
    2. 找到最后一条 user 消息作为重试输入
    3. 调用 run_agent_stream 重新推理（自动产生新的 round_number）
    4. 新的 assistant 消息追加到 DB（append-only，旧消息保留）
    5. SSE 流式返回推理过程 + 新回复
    """
    session_id = body.session_id

    # 验证会话存在
    existing = await get_session(session_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在")

    # 加载会话全部消息
    all_messages = await get_messages_by_session(session_id, page=1, page_size=1000)
    if not all_messages:
        raise HTTPException(status_code=400, detail="会话中没有消息，无法重试")

    # 找到最后一条 user 消息
    last_user_msg = None
    for msg in reversed(all_messages):
        if msg.role == "user":
            last_user_msg = msg
            break

    if not last_user_msg:
        raise HTTPException(status_code=400, detail="没有找到用户消息，无法重试")

    # 构建历史上下文（重试消息之前的历史，不含之前的 assistant 回复）
    # 策略：取最后一条 user 消息之前的所有消息作为 history
    retry_input = last_user_msg.content

    # 加载 LLM 需要的历史格式
    history = await load_session_history(session_id)

    async def retry_event_generator():
        """重试 SSE 事件生成器"""
        import json as _json

        full_reply = ""
        session_id_final = session_id

        try:
            async for event in run_agent_stream(
                user_input=retry_input,
                session_id=session_id,
                history=history,
            ):
                event_type = event.get("event", "unknown")
                # 标记为重试事件，前端可据此区分
                event["retry"] = True
                yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

                if event_type == "output":
                    full_reply = event.get("reply", "")
                    session_id_final = event.get("session_id", session_id)

                if event_type == "done":
                    session_id_final = event.get("session_id", session_id)

        except Exception as e:
            logger.error("重试对话异常: %s", e, exc_info=True)
            error_event = {"event": "error", "detail": f"{type(e).__name__}: {e}", "retry": True}
            yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return

        # 保存新的助手回复到 DB
        try:
            if full_reply:
                await append_message(session_id=session_id_final, role="assistant", content=full_reply)
            await touch_session(session_id_final)
        except Exception as db_err:
            logger.warning("重试后保存助手回复失败: %s", db_err)

    return StreamingResponse(
        retry_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
#  内部辅助函数
# ============================================================

def _generate_session_id() -> str:
    """生成新的会话 ID"""
    return f"sess_{uuid.uuid4().hex[:12]}"


def _make_title(message: str, max_len: int = 20) -> str:
    """从用户消息中提取会话标题"""
    cleaned = message.replace('\n', ' ').replace('\r', '').strip()
    if len(cleaned) > max_len:
        return cleaned[:max_len] + '...'
    return cleaned if cleaned else '新对话'
