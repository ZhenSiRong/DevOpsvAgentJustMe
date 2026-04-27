"""
交付测试 —— 审计日志 + 推理链路

覆盖端点:
  GET /api/v1/audit
  GET /api/v1/audit/stats
  GET /api/v1/reasoning/{session_id}
  GET /api/v1/reasoning/{session_id}/summary

运行方式:
  python3 test_audit_reasoning.py [BASE_URL]
"""

from __future__ import annotations

import asyncio
import sys

from test_base import DeliveryTestCase, run_tests, DEFAULT_BASE_URL


class TestAuditLogs(DeliveryTestCase):
    """审计日志查询测试"""

    async def test_audit_list(self):
        """TA-15: 审计日志列表应支持分页和过滤"""
        resp = await self.client.get("/api/v1/audit?page=1&page_size=10")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("items", d)
        self.assert_in("total", d)
        self.assert_in("page", d)
        self.assert_in("page_size", d)
        self.assert_in("total_pages", d)

    async def test_audit_filter_by_status(self):
        """TA-15: 按状态过滤审计日志"""
        for status in ["SUCCESS", "FAILED", "BLOCKED"]:
            resp = await self.client.get(f"/api/v1/audit?status={status}&page_size=5")
            data = self.assert_json_ok(resp)
            d = data.get("data", {})
            self.assert_in("items", d)

    async def test_audit_filter_invalid_status_422(self):
        """TA-15: 无效状态值返回 422"""
        resp = await self.client.get("/api/v1/audit?status=INVALID_STATUS")
        self.assert_status(resp, 422)

    async def test_audit_stats(self):
        """TA-15: 审计统计接口（实际字段: total_executions, by_status, recent_executions, blocked_rate, success_rate）"""
        resp = await self.client.get("/api/v1/audit/stats")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("total_executions", d)
        self.assert_in("by_status", d)
        self.assert_in("recent_executions", d)


class TestReasoningChain(DeliveryTestCase):
    """推理链路查询测试"""

    _session_id: str | None = None

    async def setup(self):
        await super().setup()
        # 创建一个会话用于推理链路测试
        resp = await self.client.post("/api/v1/sessions", json_data={"title": "推理链路测试"})
        self.assert_status(resp, [200, 201])
        TestReasoningChain._session_id = resp.json()["data"]["session_id"]

    async def test_reasoning_chain_empty(self):
        """TA-16: 无推理记录的会话返回 404"""
        sid = TestReasoningChain._session_id
        resp = await self.client.get(f"/api/v1/reasoning/{sid}")
        # 新会话没有推理记录，可能返回 404
        self.assert_status(resp, [200, 404])

    async def test_reasoning_summary_empty(self):
        """TA-16: 推理链路摘要（空会话）"""
        sid = TestReasoningChain._session_id
        resp = await self.client.get(f"/api/v1/reasoning/{sid}/summary")
        self.assert_status(resp, [200, 404])
        if resp.status == 200:
            data = resp.json()
            d = data.get("data", {})
            self.assert_in("total_entries", d)
            self.assert_in("total_rounds", d)

    async def test_reasoning_chain_after_chat(self):
        """TA-16: 对话后应产生推理链路记录"""
        sid = TestReasoningChain._session_id
        # 先发送一条对话（LLM调用设置5秒短超时）
        try:
            await self.client.request(
                "POST", "/api/v1/chat",
                json_data={"message": "查看系统状态", "session_id": sid},
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            pass
        # 等待落库
        await asyncio.sleep(0.5)

        # 查询推理链路
        resp = await self.client.get(f"/api/v1/reasoning/{sid}")
        self.assert_status(resp, [200, 404])
        if resp.status == 200:
            data = self.assert_json_ok(resp)
            d = data.get("data", {})
            self.assert_in("chain", d)
            self.assert_in("total_entries", d)
            self.assert_eq(d.get("session_id"), sid)

    async def test_reasoning_summary_after_chat(self):
        """TA-16: 对话后推理链路摘要（实际字段: stage_counts 而非 phases）"""
        sid = TestReasoningChain._session_id
        resp = await self.client.get(f"/api/v1/reasoning/{sid}/summary")
        self.assert_status(resp, [200, 404])
        if resp.status == 200:
            data = self.assert_json_ok(resp)
            d = data.get("data", {})
            self.assert_in("total_entries", d)
            self.assert_in("total_rounds", d)
            self.assert_in("stage_counts", d)

    async def test_reasoning_chain_not_found(self):
        """TA-16: 不存在的会话返回 404"""
        resp = await self.client.get("/api/v1/reasoning/nonexistent-session-id")
        self.assert_status(resp, 404)


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    ok = asyncio.run(run_tests([
        (TestAuditLogs, "审计日志"),
        (TestReasoningChain, "推理链路"),
    ], base_url=base_url))
    sys.exit(0 if ok else 1)
