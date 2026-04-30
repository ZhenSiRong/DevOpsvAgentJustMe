"""多模型路由 + 熔断自动故障转移

避免单模型/单厂商故障导致 Agent 任务中断。

核心组件：
- ModelPool:  多模型池（按优先级排列）
- CircuitBreaker: 熔断器（N 次连续失败 → 暂时下线 → 定时恢复）
- ModelRouter: 路由层（自动选择健康模型，透明切换）

配置来源：
- 默认模型池：代码硬编码（MiniMax → DeepSeek → Qwen）
- 运行时覆盖：configs 表 model_pool 键（JSON数组格式）
- 动态管理：可通过 Settings 页面增删模型

架构：
    Agent 调用
       ↓
    ModelRouter.route()
       ↓
    从池中选第一个 HEALTHY 模型
       ↓
    调用 LLM API
       ├─ 成功 → 返回结果
       └─ 失败 → CircuitBreaker.record_failure()
                → 尝试下一个模型
                → 直到成功或全部失败
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
#  数据模型
# ============================================================

class ModelStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # 少数失败，仍可用
    CIRCUIT_OPEN = "open"   # 熔断中，暂不可用


@dataclass
class ModelEndpoint:
    """单个模型端点"""
    name: str                               # MiniMax-M2.1 / DeepSeek-V3 / Qwen-Plus
    base_url: str                           # https://api.minimaxi.com/v1
    api_key: str                            # sk-xxx
    model_id: str                           # MiniMax-M2.1
    protocol: str = "openai"                # openai | anthropic
    priority: int = 0                       # 越小越优先 (0=主, 1=备, 2=兜底)
    status: ModelStatus = ModelStatus.HEALTHY
    failure_count: int = 0                  # 连续失败次数
    last_failure: float = 0.0               # 最后一次失败时间
    cooldown_until: float = 0.0             # 冷却到何时
    total_calls: int = 0                    # 总调用次数
    total_failures: int = 0                 # 总失败次数


class CircuitBreaker:
    """熔断器：连续失败 N 次后暂时下线，定时恢复"""

    FAILURE_THRESHOLD = 3        # 连续失败 3 次触发熔断
    COOLDOWN_SECONDS = 30        # 熔断 30 秒后尝试恢复
    HALF_OPEN_MAX_CALLS = 1      # 半开状态最多允许 1 次探测调用

    def __init__(self) -> None:
        self._endpoints: dict[str, ModelEndpoint] = {}

    def register(self, ep: ModelEndpoint) -> None:
        self._endpoints[ep.name] = ep

    def record_success(self, name: str) -> None:
        """记录一次成功调用"""
        ep = self._endpoints.get(name)
        if ep is None:
            return
        ep.total_calls += 1
        ep.failure_count = 0  # 重置失败计数
        # 从熔断中恢复
        if ep.status == ModelStatus.CIRCUIT_OPEN:
            logger.info("模型恢复: %s (熔断后探测成功)", name)
            ep.status = ModelStatus.HEALTHY
            ep.cooldown_until = 0

    def record_failure(self, name: str) -> None:
        """记录一次失败调用"""
        ep = self._endpoints.get(name)
        if ep is None:
            return
        ep.total_calls += 1
        ep.total_failures += 1
        ep.failure_count += 1
        ep.last_failure = time.monotonic()

        if ep.failure_count >= self.FAILURE_THRESHOLD:
            ep.status = ModelStatus.CIRCUIT_OPEN
            ep.cooldown_until = time.monotonic() + self.COOLDOWN_SECONDS
            logger.warning("模型熔断: %s (连续 %d 次失败, 冷却 %ds)",
                           name, ep.failure_count, self.COOLDOWN_SECONDS)

    def is_available(self, name: str) -> bool:
        """检查模型是否可用（未被熔断或已恢复）"""
        ep = self._endpoints.get(name)
        if ep is None:
            return False

        if ep.status == ModelStatus.HEALTHY:
            return True

        # 检查是否冷却完毕，可以尝试半开
        if ep.status == ModelStatus.CIRCUIT_OPEN:
            if time.monotonic() >= ep.cooldown_until:
                logger.info("模型冷却完毕，进入半开状态: %s", name)
                ep.status = ModelStatus.DEGRADED
                return True  # 允许一次探测调用
            return False

        return True  # DEGRADED 状态


class ModelRouter:
    """
    多模型路由器。

    使用方式：
        router = ModelRouter()
        result = await router.route_and_call(messages, tools, temperature)
    """

    def __init__(self) -> None:
        self._breaker = CircuitBreaker()
        self._pool: list[ModelEndpoint] = []
        self._lock = asyncio.Lock()
        self._init_default_pool()

    def _init_default_pool(self) -> None:
        """初始化默认模型池（三级梯队）—— 从 Settings 和环境变量读取"""
        import os
        from ..config import get_settings
        settings = get_settings()

        defaults = [
            ModelEndpoint(
                name="MiniMax-M2.1",
                base_url=settings.llm_base_url or "https://api.minimaxi.com/v1",
                api_key=settings.llm_api_key or os.environ.get("LLM_API_KEY", ""),
                model_id=settings.llm_model or "MiniMax-M2.1",
                protocol="openai",
                priority=0,
            ),
            ModelEndpoint(
                name="DeepSeek-V3",
                base_url="https://api.deepseek.com/v1",
                api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
                model_id="deepseek-chat",
                protocol="openai",
                priority=1,
            ),
            ModelEndpoint(
                name="Qwen-Plus",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key=os.environ.get("QWEN_API_KEY", ""),
                model_id="qwen-plus",
                protocol="openai",
                priority=2,
            ),
        ]

        # 只添加 api_key 非空的模型
        for ep in defaults:
            if ep.api_key:
                self._pool.append(ep)
                self._breaker.register(ep)
                logger.info("模型已注册: %s (优先级=%d)", ep.name, ep.priority)

        # 按优先级排序
        self._pool.sort(key=lambda e: e.priority)

        if not self._pool:
            logger.warning("没有可用的模型端点！请设置 LLM_API_KEY 等环境变量")

    async def _load_runtime_pool(self) -> None:
        """从 configs 表加载运行时模型池配置（如果存在）"""
        try:
            import json
            from ..db.config import get_config
            raw = await get_config("model_pool")
            if raw:
                custom = json.loads(raw)
                # 清除旧池并重新注册
                self._pool.clear()
                for item in custom:
                    ep = ModelEndpoint(
                        name=item.get("name", ""),
                        base_url=item.get("base_url", ""),
                        api_key=item.get("api_key", ""),
                        model_id=item.get("model_id", ""),
                        protocol=item.get("protocol", "openai"),
                        priority=item.get("priority", 0),
                    )
                    if ep.api_key and ep.base_url:
                        self._pool.append(ep)
                        self._breaker.register(ep)
                self._pool.sort(key=lambda e: e.priority)
                logger.info("运行时模型池加载: %d 个端点", len(self._pool))
        except Exception:
            pass  # 回退到默认池

    async def route_and_call(
        self,
        messages: list[Any],
        tools: list[Any] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """
        自动路由到健康模型并执行调用。

        失败时自动切换到下一个模型，直到成功或全部尝试完毕。
        """
        # 首次调用时加载运行时配置
        if not self._pool:
            await self._load_runtime_pool()

        errors = []
        for ep in self._pool:
            if not self._breaker.is_available(ep.name):
                logger.debug("跳过不可用模型: %s (状态=%s)", ep.name, ep.status)
                continue

            logger.info("调用模型: %s (%s://%s)", ep.name, ep.protocol, ep.base_url[:40])
            start = time.monotonic()

            try:
                result = await _call_single_model(
                    endpoint=ep,
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                elapsed = time.monotonic() - start
                self._breaker.record_success(ep.name)
                logger.info("模型调用成功: %s (%.2fs)", ep.name, elapsed)
                return result

            except Exception as e:
                elapsed = time.monotonic() - start
                self._breaker.record_failure(ep.name)
                err_msg = f"{type(e).__name__}: {str(e)[:100]}"
                errors.append(f"[{ep.name}] {err_msg}")
                logger.warning("模型调用失败: %s (%.2fs) → 尝试下一个", ep.name, elapsed)

        # 全部失败
        raise RuntimeError(
            f"所有模型均不可用 (尝试 {len(self._pool)} 个): {'; '.join(errors)}"
        )

    def get_pool_status(self) -> list[dict]:
        """获取模型池状态（供监控 API 使用）"""
        return [
            {
                "name": ep.name,
                "status": ep.status,
                "priority": ep.priority,
                "total_calls": ep.total_calls,
                "total_failures": ep.total_failures,
                "failure_rate": (
                    f"{ep.total_failures / max(ep.total_calls, 1) * 100:.1f}%"
                ),
            }
            for ep in self._pool
        ]


# ============================================================
#  单模型调用（复用现有 call_llm 的逻辑）
# ============================================================

async def _call_single_model(
    endpoint: ModelEndpoint,
    messages: list[Any],
    tools: list[Any] | None,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    """调用单个模型端点"""
    from .llm_client import call_llm, LLMProtocol

    response = await call_llm(
        messages=messages,
        protocol=LLMProtocol(endpoint.protocol),
        tools=tools or [],
        base_url=endpoint.base_url,
        api_key=endpoint.api_key,
        model=endpoint.model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        # 单模型调用不启用跨协议 fallback（由路由层管理）
        fallback_base_url="",
        fallback_api_key="",
        fallback_model="",
    )

    return {
        "reply_text": response.reply_text,
        "tool_calls": response.tool_calls,
        "finish_reason": response.finish_reason,
        "protocol_used": response.protocol_used,
        "usage": response.usage,
        "model": endpoint.name,
    }


# ============================================================
#  全局单例
# ============================================================

_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


async def call_with_routing(
    messages: list[Any],
    tools: list[Any] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """便捷函数：路由调用（透明替代原有 call_llm）"""
    return await get_model_router().route_and_call(
        messages=messages,
        tools=tools,
        temperature=temperature,
        max_tokens=max_tokens,
    )


__all__ = [
    "ModelRouter",
    "ModelEndpoint",
    "ModelStatus",
    "CircuitBreaker",
    "get_model_router",
    "call_with_routing",
]
