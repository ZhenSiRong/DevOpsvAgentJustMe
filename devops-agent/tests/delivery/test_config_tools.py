"""
交付测试 —— 系统配置管理 + 动态工具管理

覆盖端点:
  GET    /api/v1/config
  GET    /api/v1/config/llm
  PUT    /api/v1/config
  DELETE /api/v1/config/{key}
  POST   /api/v1/config/reset-all
  POST   /api/v1/config/detect
  GET    /api/v1/tools
  POST   /api/v1/tools
  GET    /api/v1/tools/{name}

运行方式:
  python3 test_config_tools.py [BASE_URL]
"""

from __future__ import annotations

import asyncio
import sys

from test_base import DeliveryTestCase, run_tests, DEFAULT_BASE_URL


class TestConfigManagement(DeliveryTestCase):
    """系统配置管理测试"""

    async def test_get_all_config(self):
        """TA-13: 获取全部配置（config路由直接返回dict，非APIResponse包装）"""
        resp = await self.client.get("/api/v1/config")
        self.assert_status(resp, 200)
        data = resp.json()
        self.assert_true(data is not None)
        # config.py 直接返回 {"llm": ..., "overrides": ...}
        self.assert_in("llm", data)
        self.assert_in("overrides", data)

    async def test_get_llm_config(self):
        """TA-13: 获取 LLM 配置（config/llm 返回 LLMConfigResponse 直接序列化）"""
        resp = await self.client.get("/api/v1/config/llm")
        self.assert_status(resp, 200)
        data = resp.json()
        self.assert_true(data is not None)
        self.assert_in("protocol", data)
        self.assert_in("base_url", data)
        self.assert_in("model", data)
        self.assert_in("temperature", data)
        self.assert_in("max_tokens", data)
        self.assert_in("items", data)
        # api_key 应脱敏
        self.assert_in("api_key_masked", data)

    async def test_update_config(self):
        """TA-13: 更新配置并验证生效"""
        # 先更新 temperature
        resp = await self.client.put("/api/v1/config", json_data={
            "configs": [{"key": "llm.temperature", "value": "0.5"}]
        })
        self.assert_status(resp, 200)
        data = resp.json()
        # ConfigUpdateResponse 直接序列化
        self.assert_in("updated", data)
        self.assert_in("llm.temperature", data["updated"])

        # 验证已更新（value 可能是字符串或数字）
        resp2 = await self.client.get("/api/v1/config/llm")
        data2 = resp2.json()
        items = data2.get("items", [])
        temp_item = next((i for i in items if i["key"] == "llm.temperature"), None)
        self.assert_true(temp_item is not None)
        val = temp_item.get("value")
        self.assert_true(str(val) == "0.5" or val == 0.5)
        self.assert_eq(temp_item.get("is_overridden"), True)

    async def test_update_config_rejected_prefix(self):
        """TA-13: 不允许的 key 前缀应被拒绝"""
        resp = await self.client.put("/api/v1/config", json_data={
            "configs": [{"key": "app.name", "value": "hacked"}]
        })
        self.assert_status(resp, 200)
        data = resp.json()
        self.assert_true(len(data.get("errors", [])) > 0)

    async def test_reset_config(self):
        """TA-13: 重置配置恢复默认值"""
        resp = await self.client.post("/api/v1/config/reset-all", json_data={})
        self.assert_status(resp, 200)
        data = resp.json()
        # reset-all 直接返回 {"message": ..., "deleted_keys": ..., "count": ...}
        self.assert_in("deleted_keys", data)
        self.assert_in("count", data)

        # 验证 temperature 已恢复默认值
        resp2 = await self.client.get("/api/v1/config/llm")
        data2 = resp2.json()
        items = data2.get("items", [])
        temp_item = next((i for i in items if i["key"] == "llm.temperature"), None)
        self.assert_true(temp_item is not None)
        self.assert_eq(temp_item.get("is_overridden"), False)

    async def test_delete_config_key(self):
        """TA-13: 删除单个配置键"""
        # 先设置一个值
        await self.client.put("/api/v1/config", json_data={
            "configs": [{"key": "llm.max_tokens", "value": "2048"}]
        })
        # 再删除
        resp = await self.client.delete("/api/v1/config/llm.max_tokens")
        self.assert_status(resp, 204)

    async def test_detect_config_bad_url(self):
        """TA-13: 探测错误 URL 应返回失败"""
        resp = await self.client.post("/api/v1/config/detect", json_data={
            "base_url": "https://example.com/wrong",
            "api_key": "sk-fake",
            "model": "fake-model",
            "apply": False,
        })
        self.assert_status(resp, 200)
        data = resp.json()
        # DetectResponse 直接序列化
        self.assert_eq(data.get("success"), False)
        self.assert_in("error", data)


class TestToolManagement(DeliveryTestCase):
    """动态工具管理测试"""

    async def test_list_tools(self):
        """TA-14: 工具列表应返回已注册工具（ToolListResponse: {items, total}）"""
        resp = await self.client.get("/api/v1/tools")
        self.assert_status(resp, 200)
        data = resp.json()
        self.assert_true(data is not None)
        # ToolListResponse 直接返回 {"items": [...], "total": N}
        self.assert_in("items", data)
        self.assert_in("total", data)

    async def test_get_tool_by_name(self):
        """TA-14: 按名称获取工具详情（tools路由使用 tool_id: int，非name）"""
        # 先获取列表
        resp = await self.client.get("/api/v1/tools")
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return  # 没有动态工具可测

        tool_id = items[0].get("id", 1)
        resp2 = await self.client.get(f"/api/v1/tools/{tool_id}")
        data2 = resp2.json()
        self.assert_in("name", data2)
        self.assert_in("description", data2)

    async def test_get_tool_not_found(self):
        """TA-14: 不存在的工具 ID 返回 404（注意路由参数是 int，传字符串会 422）"""
        resp = await self.client.get("/api/v1/tools/99999")
        self.assert_status(resp, 404)


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    ok = asyncio.run(run_tests([
        (TestConfigManagement, "系统配置管理"),
        (TestToolManagement, "动态工具管理"),
    ], base_url=base_url))
    sys.exit(0 if ok else 1)
