"""
交付测试基类 —— 统一测试框架

用法：
    from test_base import DeliveryTestCase, run_tests

    class TestMyAPI(DeliveryTestCase):
        async def test_something(self):
            resp = await self.get("/api/v1/health")
            self.assert_eq(resp.status, 200)
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any


# ============================================================
#  配置
# ============================================================

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


# ============================================================
#  简易 HTTP 客户端（基于 urllib，通过 asyncio.to_thread 异步化）
# ============================================================

import urllib.request
import urllib.error


class SimpleHTTPClient:
    """基于 urllib 的 HTTP 客户端，通过 asyncio.to_thread 包装为异步接口。
    不依赖 httpx/aiohttp，利用 Python 标准库实现可靠的 HTTP/1.1 通信。
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def _build_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self.base_url}{path}"

    def _sync_request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
        extra_headers: dict | None = None,
    ) -> "HTTPResponse":
        """同步 HTTP 请求（在单独线程中运行）"""
        url = self._build_url(path)
        req = urllib.request.Request(url, method=method.upper())
        req.add_header("Accept", "application/json")

        if extra_headers:
            for k, v in extra_headers.items():
                req.add_header(k, v)

        body_bytes = b""
        if json_data is not None:
            body_bytes = json.dumps(json_data, ensure_ascii=False).encode("utf-8")
            req.add_header("Content-Type", "application/json")
            req.add_header("Content-Length", str(len(body_bytes)))
            req.data = body_bytes

        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                body = resp.read()
                return HTTPResponse(
                    status=resp.status,
                    body=body,
                    text=body.decode("utf-8", errors="replace"),
                    headers=dict(resp.headers),
                )
        except urllib.error.HTTPError as e:
            body = e.read()
            return HTTPResponse(
                status=e.code,
                body=body,
                text=body.decode("utf-8", errors="replace"),
                headers=dict(e.headers),
            )
        except Exception as e:
            return HTTPResponse(status=0, body=b"", text=f"请求失败: {e}", headers={})

    async def request(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
        headers: dict | None = None,
        timeout: float = 35.0,
    ) -> "HTTPResponse":
        return await asyncio.wait_for(
            asyncio.to_thread(self._sync_request, method, path, json_data, headers),
            timeout=timeout,
        )

    async def get(self, path: str, headers: dict | None = None) -> "HTTPResponse":
        return await self.request("GET", path, headers=headers)

    async def post(self, path: str, json_data: dict | None = None, headers: dict | None = None) -> "HTTPResponse":
        return await self.request("POST", path, json_data=json_data, headers=headers)

    async def put(self, path: str, json_data: dict | None = None, headers: dict | None = None) -> "HTTPResponse":
        return await self.request("PUT", path, json_data=json_data, headers=headers)

    async def delete(self, path: str, headers: dict | None = None) -> "HTTPResponse":
        return await self.request("DELETE", path, headers=headers)


@dataclass
class HTTPResponse:
    status: int
    body: bytes
    text: str
    headers: dict[str, str]

    def json(self) -> Any:
        """解析 JSON 响应体"""
        try:
            return json.loads(self.text)
        except json.JSONDecodeError:
            return None


# ============================================================
#  测试基类
# ============================================================

@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float
    detail: str = ""
    error: str = ""


class DeliveryTestCase:
    """交付测试基类"""

    base_url: str = DEFAULT_BASE_URL
    client: SimpleHTTPClient | None = None

    async def setup(self):
        """每个测试类执行前的初始化"""
        self.client = SimpleHTTPClient(self.base_url)

    async def teardown(self):
        """每个测试类执行后的清理"""
        pass

    # ---- 断言辅助 ----

    def assert_eq(self, actual: Any, expected: Any, msg: str = ""):
        if actual != expected:
            raise AssertionError(f"{msg or '断言失败'}: expected {expected!r}, got {actual!r}")

    def assert_true(self, value: bool, msg: str = ""):
        if not value:
            raise AssertionError(msg or "期望为 True")

    def assert_in(self, item: Any, container: Any, msg: str = ""):
        if item not in container:
            raise AssertionError(f"{msg or '断言失败'}: {item!r} not in {container!r}")

    def assert_status(self, resp: HTTPResponse, expected: int | list[int]):
        """断言 HTTP 状态码"""
        if isinstance(expected, int):
            expected = [expected]
        if resp.status not in expected:
            raise AssertionError(
                f"HTTP 状态码断言失败: expected {expected}, got {resp.status}, body={resp.text[:200]}"
            )

    def assert_json_ok(self, resp: HTTPResponse, msg: str = ""):
        """断言响应是 JSON 且结构正常"""
        self.assert_status(resp, [200, 201])
        data = resp.json()
        if data is None:
            raise AssertionError(f"{msg} 响应不是有效 JSON: {resp.text[:200]}")
        if isinstance(data, dict) and "data" not in data and "error" not in data:
            # 某些端点直接返回 data 内容
            pass
        return data


# ============================================================
#  测试运行器
# ============================================================

@dataclass
class TestSuiteResult:
    suite_name: str
    results: list[TestResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)


class TestRunner:
    """收集并运行所有测试类"""

    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url
        self.suites: list[TestSuiteResult] = []

    async def run_class(self, test_class: type[DeliveryTestCase], suite_name: str) -> TestSuiteResult:
        """运行一个测试类中的所有 test_* 方法"""
        instance = test_class()
        instance.base_url = self.base_url
        await instance.setup()

        suite = TestSuiteResult(suite_name=suite_name)

        # 收集所有 test_* 方法
        methods = [
            (name, getattr(instance, name))
            for name in dir(instance)
            if name.startswith("test_") and asyncio.iscoroutinefunction(getattr(instance, name))
        ]
        methods.sort(key=lambda x: x[0])

        for name, method in methods:
            start = time.monotonic()
            try:
                await method()
                duration = (time.monotonic() - start) * 1000
                suite.results.append(TestResult(name=name, passed=True, duration_ms=duration))
            except AssertionError as e:
                duration = (time.monotonic() - start) * 1000
                suite.results.append(TestResult(name=name, passed=False, duration_ms=duration, error=str(e)))
            except Exception as e:
                duration = (time.monotonic() - start) * 1000
                suite.results.append(TestResult(
                    name=name, passed=False, duration_ms=duration,
                    error=f"{type(e).__name__}: {e}",
                ))

        await instance.teardown()
        self.suites.append(suite)
        return suite

    def print_report(self):
        """打印测试报告"""
        print("\n" + "=" * 70)
        print("  DevOps Agent 交付测试报告")
        print("=" * 70)

        total_passed = 0
        total_failed = 0

        for suite in self.suites:
            print(f"\n  📦 {suite.suite_name}")
            print("  " + "-" * 66)
            for r in suite.results:
                icon = "✅ PASS" if r.passed else "❌ FAIL"
                print(f"  {icon}  {r.name:<45}  {r.duration_ms:>6.1f}ms")
                if not r.passed and r.error:
                    print(f"       └─> {r.error[:120]}")
            total_passed += suite.passed_count
            total_failed += suite.failed_count

        print("\n" + "=" * 70)
        total = total_passed + total_failed
        rate = (total_passed / total * 100) if total > 0 else 0
        print(f"  总计: {total_passed}/{total} 通过  ({rate:.1f}%)")
        if total_failed == 0:
            print("  🎉 全部通过！")
        else:
            print(f"  ⚠️  {total_failed} 个测试失败")
        print("=" * 70 + "\n")

        return total_failed == 0


async def run_tests(test_classes: list[tuple[type[DeliveryTestCase], str]], base_url: str = DEFAULT_BASE_URL) -> bool:
    """便捷函数：运行一组测试类并打印报告"""
    runner = TestRunner(base_url)
    for cls, name in test_classes:
        await runner.run_class(cls, name)
    return runner.print_report()
