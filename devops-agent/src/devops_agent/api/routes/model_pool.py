"""模型路由管理 API

端点：
- GET  /api/v1/models/pool     查看模型池状态（含熔断/成功率）
- PUT  /api/v1/models/pool     更新模型池配置
- POST /api/v1/models/reset    重置所有熔断器
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..schemas import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/models", tags=["模型路由"])


class ModelPoolItem(BaseModel):
    name: str
    base_url: str
    api_key: str
    model_id: str
    protocol: str = "openai"
    priority: int = 0


class ModelPoolUpdate(BaseModel):
    models: list[ModelPoolItem] = Field(..., min_length=1)


@router.get("/pool", response_model=APIResponse, summary="查看模型池状态")
async def get_model_pool() -> APIResponse:
    """返回所有模型端点的状态（含熔断、成功率）。"""
    from ...agent.model_router import get_model_router
    router = get_model_router()
    return APIResponse(data={"models": router.get_pool_status()})


@router.put("/pool", response_model=APIResponse, summary="更新模型池配置")
async def update_model_pool(body: ModelPoolUpdate) -> APIResponse:
    """更新运行时模型池配置（持久化到 configs 表）"""
    try:
        import json
        from ...db.config import set_config
        pool_data = [m.model_dump() for m in body.models]
        await set_config("model_pool", json.dumps(pool_data, ensure_ascii=False))
        logger.info("模型池已更新: %d 个模型", len(pool_data))
        return APIResponse(data={"count": len(pool_data)}, message="模型池已更新，下次调用生效")
    except Exception as e:
        return APIResponse(code=500, message=str(e))


@router.post("/reset", response_model=APIResponse, summary="重置所有熔断器")
async def reset_circuit_breakers() -> APIResponse:
    """强制恢复所有被熔断的模型为健康状态。"""
    from ...agent.model_router import get_model_router, CircuitBreaker
    router = get_model_router()
    reset_count = 0
    for ep in router._pool:
        if ep.status != "healthy":
            ep.status = "healthy"  # type: ignore
            ep.failure_count = 0
            reset_count += 1
    return APIResponse(data={"reset_count": reset_count}, message=f"已重置 {reset_count} 个模型")


__all__ = ["router"]
