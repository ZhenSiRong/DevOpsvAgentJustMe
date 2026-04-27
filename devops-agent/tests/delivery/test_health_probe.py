"""
交付测试 —— 健康检查 + OS 环境探针

覆盖端点:
  GET  /health
  GET  /api/v1/info
  GET  /api/v1/probe/disk
  GET  /api/v1/probe/processes
  GET  /api/v1/probe/network
  GET  /api/v1/probe/logs

运行方式:
  python3 test_health_probe.py [BASE_URL]
"""

from __future__ import annotations

import asyncio
import sys

from test_base import DeliveryTestCase, run_tests, DEFAULT_BASE_URL


class TestHealthEndpoint(DeliveryTestCase):
    """健康检查端点测试"""

    async def test_health_returns_200(self):
        """TA-01: 健康检查应返回 200"""
        resp = await self.client.get("/health")
        self.assert_status(resp, 200)

    async def test_health_has_required_fields(self):
        """TA-01: 响应应包含 status/app/version/db_connected/uptime_seconds"""
        resp = await self.client.get("/health")
        data = self.assert_json_ok(resp)
        self.assert_in("status", data)
        self.assert_in("app", data)
        self.assert_in("version", data)
        self.assert_in("db_connected", data)
        self.assert_in("uptime_seconds", data)

    async def test_info_returns_modules(self):
        """TA-01: /api/v1/info 应返回模块就绪状态"""
        resp = await self.client.get("/api/v1/info")
        data = self.assert_json_ok(resp)
        self.assert_in("data", data)
        d = data["data"]
        self.assert_in("modules", d)
        self.assert_in("llm_protocol", d)
        self.assert_in("llm_model", d)


class TestProbeDisk(DeliveryTestCase):
    """磁盘探针测试"""

    async def test_probe_disk_returns_usage(self):
        """TA-02: 磁盘探针应返回使用率信息"""
        resp = await self.client.get("/api/v1/probe/disk")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("usage", d)

    async def test_probe_disk_with_path_param(self):
        """TA-02: 带 path 参数的磁盘探针"""
        resp = await self.client.get("/api/v1/probe/disk?path=/tmp")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_eq(d.get("path"), "/tmp")


class TestProbeProcesses(DeliveryTestCase):
    """进程探针测试"""

    async def test_probe_processes_returns_list(self):
        """TA-03: 进程探针应返回进程列表"""
        resp = await self.client.get("/api/v1/probe/processes?limit=10")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("processes", d)
        self.assert_in("count", d)

    async def test_probe_processes_filter_by_name(self):
        """TA-03: 按名称过滤进程"""
        resp = await self.client.get("/api/v1/probe/processes?filter_by_name=python&limit=5")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("processes", d)
        self.assert_eq(d.get("filter"), "python")

    async def test_probe_processes_pid_detail(self):
        """TA-03: 按 PID 查询单个进程详情"""
        # 先获取一个有效 PID（通常 init/systemd 是 1）
        resp = await self.client.get("/api/v1/probe/processes?pid=1")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("process", d)


class TestProbeNetwork(DeliveryTestCase):
    """网络探针测试"""

    async def test_probe_network_connections(self):
        """TA-04: 网络连接探针"""
        resp = await self.client.get("/api/v1/probe/network?action=connections")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("connections", d)
        self.assert_in("count", d)

    async def test_probe_network_interfaces(self):
        """TA-04: 网络接口探针"""
        resp = await self.client.get("/api/v1/probe/network?action=interfaces")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("interfaces", d)

    async def test_probe_network_dns(self):
        """TA-04: DNS 解析探针"""
        resp = await self.client.get("/api/v1/probe/network?action=dns&hostname=localhost")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("dns", d)


class TestProbeLogs(DeliveryTestCase):
    """日志探针测试"""

    async def test_probe_logs_journalctl(self):
        """TA-05: journalctl 日志探针"""
        resp = await self.client.get("/api/v1/probe/logs?lines=5&unit=system")
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_in("logs", d)
        self.assert_in("count", d)
        self.assert_eq(d.get("mode"), "journalctl")

    async def test_probe_logs_tail_file(self):
        """TA-05: tail 文件模式"""
        resp = await self.client.get("/api/v1/probe/logs?tail_path=/var/log/messages&lines=3")
        # 文件可能不存在，接受 200 或 404
        if resp.status == 404:
            return  # 文件不存在是合理的
        data = self.assert_json_ok(resp)
        d = data.get("data", {})
        self.assert_eq(d.get("mode"), "tail")


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    ok = asyncio.run(run_tests([
        (TestHealthEndpoint, "健康检查"),
        (TestProbeDisk, "磁盘探针"),
        (TestProbeProcesses, "进程探针"),
        (TestProbeNetwork, "网络探针"),
        (TestProbeLogs, "日志探针"),
    ], base_url=base_url))
    sys.exit(0 if ok else 1)
