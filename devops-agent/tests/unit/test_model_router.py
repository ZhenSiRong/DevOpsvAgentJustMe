# tests/unit/test_model_router.py
"""多模型路由 + 熔断器单元测试"""

import pytest
from unittest.mock import AsyncMock, patch
from devops_agent.agent.model_router import (
    ModelEndpoint,
    ModelStatus,
    CircuitBreaker,
    ModelRouter,
)


class TestCircuitBreaker:
    def test_healthy_by_default(self):
        ep = ModelEndpoint(name="test", base_url="http://x", api_key="k", model_id="m")
        cb = CircuitBreaker()
        cb.register(ep)
        assert cb.is_available("test")

    def test_record_success_resets_failure_count(self):
        ep = ModelEndpoint(name="test", base_url="http://x", api_key="k", model_id="m")
        cb = CircuitBreaker()
        cb.register(ep)
        cb.record_failure("test")
        cb.record_failure("test")
        assert ep.failure_count == 2
        cb.record_success("test")
        assert ep.failure_count == 0
        assert ep.status == ModelStatus.HEALTHY

    def test_three_failures_opens_circuit(self):
        ep = ModelEndpoint(name="test", base_url="http://x", api_key="k", model_id="m")
        cb = CircuitBreaker()
        cb.register(ep)
        cb.record_failure("test")
        cb.record_failure("test")
        cb.record_failure("test")
        assert ep.status == ModelStatus.CIRCUIT_OPEN
        assert not cb.is_available("test")

    def test_missing_endpoint_returns_false(self):
        cb = CircuitBreaker()
        assert not cb.is_available("nonexistent")

    def test_total_call_counting(self):
        ep = ModelEndpoint(name="test", base_url="http://x", api_key="k", model_id="m")
        cb = CircuitBreaker()
        cb.register(ep)
        cb.record_success("test")
        cb.record_failure("test")
        assert ep.total_calls == 2
        assert ep.total_failures == 1
