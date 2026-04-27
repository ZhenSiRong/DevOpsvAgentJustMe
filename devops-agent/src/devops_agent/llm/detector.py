"""
LLM 协议自动探测模块 —— 一键识别服务协议类型

使用方式：
    result = await detect_llm_protocol(
        base_url="https://api.kimi.com/coding",
        api_key="sk-xxx",
        model="kimi-for-coding",
    )
    if result.success:
        print(f"探测到协议: {result.protocol}")
    else:
        print(f"探测失败: {result.error}")

探测策略：
1. 构造极简请求（"Say ok"），max_tokens=5，减少 token 消耗
2. 先尝试 Anthropic 协议（POST /messages），因为部分服务同时兼容两种协议时，
   Anthropic 协议的响应结构更明确（不易误判）
3. 再尝试 OpenAI 协议（POST /chat/completions）
4. 返回 200 且响应结构符合预期（含 content/choices）即判定成功
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProtocolDetectResult:
    """协议探测结果"""
    success: bool                # 是否探测成功
    protocol: str = ""           # 探测到的协议: "openai" | "anthropic" | ""
    base_url: str = ""           # 探测时使用的 base_url
    api_key: str = ""            # 探测时使用的 api_key
    model: str = ""              # 探测时使用的 model
    response_preview: str = ""   # 响应预览（前 200 字符）
    error: str = ""              # 失败原因
    openai_error: str = ""       # OpenAI 协议探测错误
    anthropic_error: str = ""    # Anthropic 协议探测错误


async def _try_openai(
    base_url: str,
    api_key: str,
    model: str,
    client: Any,
) -> tuple[bool, str, str]:
    """
    尝试 OpenAI 协议。

    Returns:
        (success: bool, preview: str, error: str)
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Say ok"}],
        "temperature": 0.0,
        "max_tokens": 5,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = await client.post(url, json=body, headers=headers, timeout=15.0)
        text = resp.text
        preview = text[:200] if text else "(empty)"

        if resp.status_code == 200:
            try:
                data = resp.json()
                # OpenAI 成功标志：choices 数组存在
                if "choices" in data and isinstance(data.get("choices"), list):
                    return True, preview, ""
                return False, preview, "响应缺少 choices 字段"
            except Exception:
                return False, preview, "响应不是有效 JSON"
        else:
            return False, preview, f"HTTP {resp.status_code}: {preview}"

    except Exception as e:
        return False, "", f"请求异常: {e}"


async def _try_anthropic(
    base_url: str,
    api_key: str,
    model: str,
    client: Any,
) -> tuple[bool, str, str]:
    """
    尝试 Anthropic 协议。

    Returns:
        (success: bool, preview: str, error: str)
    """
    url = f"{base_url.rstrip('/')}/messages"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Say ok"}],
        "max_tokens": 5,
        "temperature": 0.0,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        resp = await client.post(url, json=body, headers=headers, timeout=15.0)
        text = resp.text
        preview = text[:200] if text else "(empty)"

        if resp.status_code == 200:
            try:
                data = resp.json()
                # Anthropic 成功标志：content 数组存在
                if "content" in data and isinstance(data.get("content"), list):
                    return True, preview, ""
                return False, preview, "响应缺少 content 字段"
            except Exception:
                return False, preview, "响应不是有效 JSON"
        else:
            return False, preview, f"HTTP {resp.status_code}: {preview}"

    except Exception as e:
        return False, "", f"请求异常: {e}"


async def detect_llm_protocol(
    base_url: str,
    api_key: str,
    model: str,
) -> ProtocolDetectResult:
    """
    自动探测 LLM 服务使用的协议类型。

    同时尝试 Anthropic 和 OpenAI 两种协议，优先返回 Anthropic（因为部分
    服务同时兼容两种协议时，Anthropic 的响应结构更明确）。

    Args:
        base_url: 服务基础 URL（如 https://api.kimi.com/coding）
        api_key: API Key
        model: 模型名称（如 kimi-for-coding）

    Returns:
        ProtocolDetectResult: 探测结果
    """
    import httpx

    logger.info("开始探测 LLM 协议: base_url=%s model=%s", base_url, model)

    result = ProtocolDetectResult(
        success=False,
        base_url=base_url,
        api_key=api_key,
        model=model,
    )

    try:
        async with httpx.AsyncClient() as client:
            # 并发探测两种协议（用 asyncio.gather）
            anthropic_task = _try_anthropic(base_url, api_key, model, client)
            openai_task = _try_openai(base_url, api_key, model, client)

            anthropic_ok, anthropic_preview, anthropic_err = await anthropic_task
            openai_ok, openai_preview, openai_err = await openai_task

            result.anthropic_error = anthropic_err
            result.openai_error = openai_err

            # 优先 Anthropic（结构更明确，不易误判）
            if anthropic_ok:
                result.success = True
                result.protocol = "anthropic"
                result.response_preview = anthropic_preview
                logger.info("探测成功: Anthropic 协议 (%s)", base_url)
                return result

            if openai_ok:
                result.success = True
                result.protocol = "openai"
                result.response_preview = openai_preview
                logger.info("探测成功: OpenAI 协议 (%s)", base_url)
                return result

            # 都失败了
            result.error = (
                f"两种协议均探测失败。\n"
                f"  Anthropic: {anthropic_err}\n"
                f"  OpenAI: {openai_err}"
            )
            logger.warning("协议探测失败: %s", result.error)
            return result

    except Exception as e:
        result.error = f"探测过程异常: {e}"
        logger.error("协议探测异常: %s", e)
        return result


async def apply_detected_config(
    base_url: str,
    api_key: str,
    model: str,
) -> ProtocolDetectResult:
    """
    探测协议并自动持久化配置到数据库。

    根据探测结果，自动写入对应的 DB 配置项：
    - OpenAI: llm.protocol=openai, llm.base_url=..., llm.api_key=..., llm.model=...
    - Anthropic: llm.protocol=anthropic, llm.anthropic_base_url=..., etc.

    Returns:
        ProtocolDetectResult: 包含探测结果和任何持久化错误
    """
    from ..db.config import set_config

    result = await detect_llm_protocol(base_url, api_key, model)

    if not result.success:
        return result

    try:
        if result.protocol == "anthropic":
            await set_config("llm.protocol", "anthropic")
            await set_config("llm.anthropic_base_url", base_url)
            await set_config("llm.anthropic_api_key", api_key)
            await set_config("llm.anthropic_model", model)
            logger.info("已持久化 Anthropic 配置到 DB")
        else:
            await set_config("llm.protocol", "openai")
            await set_config("llm.base_url", base_url)
            await set_config("llm.api_key", api_key)
            await set_config("llm.model", model)
            logger.info("已持久化 OpenAI 配置到 DB")
    except Exception as e:
        result.error = f"探测成功但持久化失败: {e}"
        logger.error(result.error)

    return result
