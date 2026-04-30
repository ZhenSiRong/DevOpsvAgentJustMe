"""提示词管理中心

提供对 System Prompt 的运行时管理：
- 读取当前生效的 System Prompt
- 修改并保存（持久化到 configs 表）
- 重置为默认值
- 版本历史（最近 5 次修改）

端点：
- GET  /api/v1/prompt        获取当前 Prompt
- PUT  /api/v1/prompt        更新 Prompt
- POST /api/v1/prompt/reset  重置为默认
- GET  /api/v1/prompt/history 版本历史
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..schemas import APIResponse
from ...agent.core import build_system_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prompt", tags=["提示词管理"])

PROMPT_CONFIG_KEY = "agent.system_prompt"
PROMPT_HISTORY_KEY = "agent.system_prompt_history"

DEFAULT_PROMPT = build_system_prompt()


class PromptUpdateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000, description="新的 System Prompt")


async def get_current_prompt() -> str:
    """从 configs 表读取当前 Prompt，fallback 到默认值"""
    from ..db.config import get_config
    try:
        prompt = await get_config(PROMPT_CONFIG_KEY)
        if prompt and prompt.strip():
            return prompt
    except Exception:
        pass
    return DEFAULT_PROMPT


async def save_prompt(prompt: str) -> None:
    """保存 Prompt 到 configs 表，同时记录版本历史"""
    from ..db.config import set_config, get_config
    # 保存当前版本到历史
    try:
        history_raw = await get_config(PROMPT_HISTORY_KEY)
        history = json.loads(history_raw) if history_raw else []
    except Exception:
        history = []

    current = await get_current_prompt()
    if current != prompt:
        history.append({
            "prompt": current[:500],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # 保留最近 5 条历史
        history = history[-5:]

    await set_config(PROMPT_CONFIG_KEY, prompt)
    await set_config(PROMPT_HISTORY_KEY, json.dumps(history, ensure_ascii=False))


@router.get("", response_model=APIResponse, summary="获取当前 System Prompt")
async def get_prompt() -> APIResponse:
    prompt = await get_current_prompt()
    is_default = (prompt == DEFAULT_PROMPT)
    return APIResponse(data={
        "prompt": prompt,
        "is_default": is_default,
        "length": len(prompt),
    })


@router.put("", response_model=APIResponse, summary="更新 System Prompt")
async def update_prompt(body: PromptUpdateRequest) -> APIResponse:
    if not body.prompt.strip():
        raise HTTPException(status_code=422, detail="Prompt 不能为空")
    await save_prompt(body.prompt.strip())
    logger.info("System Prompt 已更新（%d 字符）", len(body.prompt))
    return APIResponse(message="Prompt 已更新，将在下次对话生效")


@router.post("/reset", response_model=APIResponse, summary="重置为默认 Prompt")
async def reset_prompt() -> APIResponse:
    from ..db.config import delete_config
    await delete_config(PROMPT_CONFIG_KEY)
    logger.info("System Prompt 已重置为默认")
    return APIResponse(data={"prompt": DEFAULT_PROMPT}, message="已重置为默认 Prompt")


@router.get("/history", response_model=APIResponse, summary="Prompt 修改历史")
async def prompt_history() -> APIResponse:
    from ..db.config import get_config
    try:
        raw = await get_config(PROMPT_HISTORY_KEY)
        history = json.loads(raw) if raw else []
    except Exception:
        history = []
    return APIResponse(data={"history": history, "count": len(history)})


__all__ = ["router", "get_current_prompt"]
