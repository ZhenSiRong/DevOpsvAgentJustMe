"""系统配置管理 API —— 支持运行时动态修改 LLM 等参数

设计原则：
1. Settings (.env) 提供默认值，不可通过此 API 修改
2. DB configs 表存储覆盖值，API 只操作覆盖层
3. 敏感字段（api_key）在响应中脱敏处理
4. 配置变更即时生效（下一次 Agent 对话自动读取）
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...config import get_settings, get_llm_runtime_config
from ...db.config import get_all_configs, set_config, delete_config, get_config
from ...llm.detector import detect_llm_protocol, apply_detected_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["config"])


# ============================================================
#  Pydantic 模型
# ============================================================

class LLMConfigItem(BaseModel):
    """单个 LLM 配置项（带默认值和覆盖标记）"""
    key: str
    value: Any
    default_value: Any
    is_overridden: bool
    description: str
    sensitive: bool = False  # 是否敏感（如 api_key）


class LLMConfigResponse(BaseModel):
    """LLM 配置完整响应"""
    protocol: str
    base_url: str
    api_key_masked: str  # 脱敏后的 key
    model: str
    temperature: float
    max_tokens: int
    anthropic_base_url: str
    anthropic_api_key_masked: str
    anthropic_model: str
    items: list[LLMConfigItem]


class ConfigUpdateItem(BaseModel):
    """单个配置更新项"""
    key: str = Field(..., description="配置键名，如 llm.model")
    value: str = Field(..., description="配置值（字符串，数字/bool 会自行转换）")


class ConfigUpdateRequest(BaseModel):
    """批量更新配置请求"""
    configs: list[ConfigUpdateItem] = Field(..., description="要更新的配置项列表")


class ConfigUpdateResponse(BaseModel):
    """配置更新响应"""
    updated: list[str] = Field(default_factory=list, description="成功更新的键名")
    errors: list[str] = Field(default_factory=list, description="失败的键名及原因")


class AllConfigResponse(BaseModel):
    """全部配置响应（含非 LLM 配置）"""
    llm: LLMConfigResponse
    overrides: list[dict[str, Any]]  # DB 中所有覆盖值


class DetectRequest(BaseModel):
    """协议探测请求 —— 用户只需提供基础连接信息"""
    base_url: str = Field(..., description="服务 Base URL（如 https://api.kimi.com/coding）")
    api_key: str = Field(..., description="API Key")
    model: str = Field(..., description="模型名称（如 kimi-for-coding）")
    apply: bool = Field(True, description="探测成功后是否自动持久化到 DB")


class DetectResponse(BaseModel):
    """协议探测响应"""
    success: bool
    protocol: str = Field("", description="探测到的协议: openai / anthropic / 空")
    base_url: str
    model: str
    response_preview: str = Field("", description="服务端响应预览（前200字符）")
    error: str = Field("", description="失败原因（成功时为空）")
    openai_error: str = Field("", description="OpenAI 协议探测错误")
    anthropic_error: str = Field("", description="Anthropic 协议探测错误")
    applied: bool = Field(False, description="是否已自动持久化到 DB")


# ============================================================
#  辅助函数
# ============================================================

def _mask_key(key: str) -> str:
    """脱敏 API Key：只保留前 8 和后 4 位"""
    if not key or len(key) < 16:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


LLM_CONFIG_KEYS = [
    ("llm.protocol", "str", "LLM 协议类型 (openai / anthropic)"),
    ("llm.base_url", "str", "OpenAI 协议 Base URL"),
    ("llm.api_key", "str", "OpenAI 协议 API Key", True),
    ("llm.model", "str", "OpenAI 协议模型名称"),
    ("llm.temperature", "float", "采样温度 (0.0-2.0)"),
    ("llm.max_tokens", "int", "最大生成 token 数"),
    ("llm.anthropic_base_url", "str", "Anthropic 协议 Base URL"),
    ("llm.anthropic_api_key", "str", "Anthropic 协议 API Key", True),
    ("llm.anthropic_model", "str", "Anthropic 协议模型名称"),
]


# ============================================================
#  API 端点
# ============================================================

@router.get("/llm", response_model=LLMConfigResponse)
async def get_llm_config():
    """
    获取当前 LLM 运行时配置。

    返回的是 Settings 默认值 + DB 覆盖值合并后的结果。
    同时返回每个配置项的默认值和是否被覆盖，方便前端展示。
    """
    settings = get_settings()
    llm_cfg = await get_llm_runtime_config()

    items: list[LLMConfigItem] = []

    for spec in LLM_CONFIG_KEYS:
        key = spec[0]
        # type_hint = spec[1]
        desc = spec[2]
        sensitive = spec[3] if len(spec) > 3 else False

        # 获取当前值（来自 llm_cfg）和默认值（来自 settings）
        if key == "llm.protocol":
            current = llm_cfg.protocol
            default = settings.llm_protocol
        elif key == "llm.base_url":
            current = llm_cfg.base_url
            default = settings.llm_base_url
        elif key == "llm.api_key":
            current = llm_cfg.api_key
            default = settings.llm_api_key
        elif key == "llm.model":
            current = llm_cfg.model
            default = settings.llm_model
        elif key == "llm.temperature":
            current = llm_cfg.temperature
            default = settings.llm_temperature
        elif key == "llm.max_tokens":
            current = llm_cfg.max_tokens
            default = settings.llm_max_tokens
        elif key == "llm.anthropic_base_url":
            current = llm_cfg.anthropic_base_url
            default = settings.anthropic_base_url
        elif key == "llm.anthropic_api_key":
            current = llm_cfg.anthropic_api_key
            default = settings.anthropic_api_key
        elif key == "llm.anthropic_model":
            current = llm_cfg.anthropic_model
            default = settings.anthropic_model
        else:
            continue

        display_current = _mask_key(current) if sensitive else current
        display_default = _mask_key(default) if sensitive else default

        items.append(LLMConfigItem(
            key=key,
            value=display_current,
            default_value=display_default,
            is_overridden=current != default,
            description=desc,
            sensitive=sensitive,
        ))

    return LLMConfigResponse(
        protocol=llm_cfg.protocol,
        base_url=llm_cfg.base_url,
        api_key_masked=_mask_key(llm_cfg.api_key),
        model=llm_cfg.model,
        temperature=llm_cfg.temperature,
        max_tokens=llm_cfg.max_tokens,
        anthropic_base_url=llm_cfg.anthropic_base_url,
        anthropic_api_key_masked=_mask_key(llm_cfg.anthropic_api_key),
        anthropic_model=llm_cfg.anthropic_model,
        items=items,
    )


@router.get("", response_model=dict)
async def get_all_config():
    """
    获取全部配置信息。

    包括：
    - LLM 运行时配置（合并后）
    - DB 中所有覆盖值（原始 key-value）
    """
    llm_resp = await get_llm_config()
    overrides = await get_all_configs()

    return {
        "llm": llm_resp.model_dump(),
        "overrides": [
            {"key": c.key, "value": _mask_key(c.value) if "api_key" in c.key else c.value, "updated_at": c.updated_at}
            for c in overrides
        ],
    }


@router.put("", response_model=ConfigUpdateResponse)
async def update_config(request: ConfigUpdateRequest):
    """
    批量更新配置。

    将配置写入 DB configs 表，覆盖 Settings 默认值。
    写入后即时生效（下一次 Agent 调用自动读取）。

    支持的 key 前缀：
    - `llm.*` — LLM 相关配置

    示例请求体：
    ```json
    {
      "configs": [
        {"key": "llm.model", "value": "MiniMax-M2.1"},
        {"key": "llm.temperature", "value": "0.5"}
      ]
    }
    ```
    """
    updated: list[str] = []
    errors: list[str] = []

    allowed_prefixes = ("llm.",)

    for item in request.configs:
        key = item.key.strip()
        value = item.value.strip() if isinstance(item.value, str) else str(item.value)

        if not key:
            errors.append("空 key 被跳过")
            continue

        # 安全检查：只允许修改已知前缀的配置
        if not any(key.startswith(p) for p in allowed_prefixes):
            errors.append(f"{key}: 不允许修改该配置键（只允许 {allowed_prefixes} 前缀）")
            continue

        try:
            await set_config(key, value)
            updated.append(key)
            logger.info("配置已更新: %s", key)
        except Exception as e:
            errors.append(f"{key}: {e}")
            logger.error("配置更新失败 %s: %s", key, e)

    return ConfigUpdateResponse(updated=updated, errors=errors)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def reset_config(key: str):
    """
    删除 DB 中的配置覆盖值，恢复为 Settings 默认值。

    路径参数 `key` 支持 URL 编码（如 `llm.model`）。
    """
    # URL 解码（FastAPI 自动处理，但如果 key 包含特殊字符需要确认）
    decoded_key = key.strip()

    success = await delete_config(decoded_key)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"配置键 '{decoded_key}' 不存在或已是默认值",
        )

    logger.info("配置已重置为默认值: %s", decoded_key)


@router.post("/reset-all", response_model=dict)
async def reset_all_config():
    """
    一键重置所有 LLM 配置为 Settings 默认值。

    删除 DB 中所有 `llm.` 前缀的配置覆盖值。
    """
    overrides = await get_all_configs()
    deleted_keys: list[str] = []

    for cfg in overrides:
        if cfg.key.startswith("llm."):
            await delete_config(cfg.key)
            deleted_keys.append(cfg.key)

    logger.info("已重置 %d 个 LLM 配置为默认值", len(deleted_keys))
    return {
        "message": "所有 LLM 配置已重置为默认值",
        "deleted_keys": deleted_keys,
        "count": len(deleted_keys),
    }


@router.post("/detect", response_model=DetectResponse)
async def detect_config(request: DetectRequest):
    """
    自动探测 LLM 服务协议类型。

    用户只需提供 base_url + api_key + model，后端同时尝试
    OpenAI 和 Anthropic 两种协议，哪个通了自动返回结果。

    若 `apply=true`（默认），探测成功后自动持久化到 DB，
    下一条对话即时生效。

    示例请求体：
    ```json
    {
      "base_url": "https://api.kimi.com/coding",
      "api_key": "sk-xxx",
      "model": "kimi-for-coding"
    }
    ```
    """
    if request.apply:
        result = await apply_detected_config(
            base_url=request.base_url,
            api_key=request.api_key,
            model=request.model,
        )
    else:
        result = await detect_llm_protocol(
            base_url=request.base_url,
            api_key=request.api_key,
            model=request.model,
        )

    return DetectResponse(
        success=result.success,
        protocol=result.protocol,
        base_url=result.base_url,
        model=result.model,
        response_preview=result.response_preview,
        error=result.error,
        openai_error=result.openai_error,
        anthropic_error=result.anthropic_error,
        applied=request.apply and result.success,
    )
