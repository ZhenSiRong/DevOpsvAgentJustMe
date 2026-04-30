"""轻量级 Token Bucket 速率限制器 —— FastAPI Middleware

实现方案：
- 内存 Token Bucket 算法（按 IP 粒度）
- 默认配置：60 requests / minute / IP（可配）
- 超限返回 429 Too Many Requests
- 自动过期清理（避免内存无限增长）

为什么自实现而非 slowapi：
- 避免额外依赖（slowapi + limits）
- pip 安装流程在 VM 上需额外步骤
- 当前并发量下内存 Token Bucket 完全够用
"""

from __future__ import annotations

import time
import asyncio
import logging
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token Bucket 算法单个 IP 的速率控制"""

    __slots__ = ("tokens", "last_refill", "rate", "capacity")

    def __init__(self, rate: float, capacity: int) -> None:
        self.tokens = float(capacity)       # 当前可用 token 数
        self.last_refill = time.monotonic() # 上次补充时间
        self.rate = rate                     # token/秒
        self.capacity = capacity             # 最大 token 数

    def consume(self, tokens: int = 1) -> bool:
        """尝试消费 token，返回是否成功"""
        now = time.monotonic()
        elapsed = now - self.last_refill
        # 补充 token（按 elapsed 时间）
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """按 IP 粒度的 Token Bucket 限流中间件

    配置通过环境变量（fallback 到默认值）：
    - RATE_LIMIT_PER_MINUTE: 每分钟允许请求数（默认 60）
    - RATE_LIMIT_BURST:      burst 容量（默认 10）

    排除路径（不受限流）：
    - /health, /docs, /redoc, /openapi.json
    """

    SKIP_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")

    def __init__(self, app, **kwargs) -> None:
        super().__init__(app, **kwargs)
        import os
        requests_per_minute = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))
        burst = int(os.environ.get("RATE_LIMIT_BURST", "10"))
        self._rate = requests_per_minute / 60.0  # tokens per second
        self._capacity = burst + requests_per_minute  # max tokens

        # 按 IP → TokenBucket
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        self._last_cleanup = time.monotonic()

        logger.info(
            "限流器已启用: %d req/min, burst=%d (rate=%.2f t/s, capacity=%d)",
            requests_per_minute, burst, self._rate, self._capacity,
        )

    async def _get_bucket(self, ip: str) -> TokenBucket:
        async with self._lock:
            bucket = self._buckets.get(ip)
            if bucket is None:
                bucket = TokenBucket(self._rate, self._capacity)
                self._buckets[ip] = bucket
            # 每 5 分钟清理一次过期桶（10分钟无请求的 IP）
            now = time.monotonic()
            if now - self._last_cleanup > 300:
                before = len(self._buckets)
                self._buckets = {
                    k: v for k, v in self._buckets.items()
                    if now - v.last_refill < 600
                }
                self._last_cleanup = now
                if before != len(self._buckets):
                    logger.debug("限流器 GC: %d -> %d 个活跃 IP", before, len(self._buckets))
            return bucket

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> RequestResponseEndpoint:
        # 排除路径直接放行
        path = request.url.path
        for prefix in self.SKIP_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # 获取客户端 IP
        client_ip = request.client.host if request.client else "unknown"

        bucket = await self._get_bucket(client_ip)
        if not bucket.consume():
            logger.warning("IP %s 触发限流", client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "请求过于频繁，请稍后再试",
                        "retry_after_seconds": 1,
                    }
                },
            )

        return await call_next(request)


__all__ = ["RateLimitMiddleware"]
