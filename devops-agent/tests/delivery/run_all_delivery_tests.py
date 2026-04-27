"""
DevOps Agent —— 交付前最终集成测试总入口

覆盖全部后端 API 端点，输出统一测试报告。

用法:
  # 1. 确保后端服务已启动
  cd /root/devops-agent && python3 -m devops_agent.api

  # 2. 运行全部交付测试
  cd tests/delivery && python3 run_all_delivery_tests.py

  # 3. 指定自定义地址
  python3 run_all_delivery_tests.py http://192.168.187.128:8000

测试套件:
  ├─ 健康检查 + OS 探针     (test_health_probe.py)
  ├─ 会话管理 + AI 对话      (test_sessions_chat.py)
  ├─ 核心安全层 API          (test_safety_api.py)
  ├─ 配置管理 + 动态工具      (test_config_tools.py)
  └─ 审计日志 + 推理链路      (test_audit_reasoning.py)

退出码:
  0 — 全部通过
  1 — 有测试失败
"""

from __future__ import annotations

import asyncio
import sys
import time

from test_base import TestRunner, DEFAULT_BASE_URL

# 导入所有测试类
from test_health_probe import (
    TestHealthEndpoint,
    TestProbeDisk,
    TestProbeProcesses,
    TestProbeNetwork,
    TestProbeLogs,
)
from test_sessions_chat import TestSessionCRUD, TestChatEndpoint
from test_safety_api import (
    TestSafetyValidator,
    TestSafetyExecute,
    TestSafetyStatus,
    TestPromptInjection,
    TestConfigGuard,
)
from test_config_tools import TestConfigManagement, TestToolManagement
from test_audit_reasoning import TestAuditLogs, TestReasoningChain


async def main(base_url: str) -> bool:
    runner = TestRunner(base_url)
    suites = [
        (TestHealthEndpoint, "1️⃣ 健康检查"),
        (TestProbeDisk, "2️⃣ 磁盘探针"),
        (TestProbeProcesses, "3️⃣ 进程探针"),
        (TestProbeNetwork, "4️⃣ 网络探针"),
        (TestProbeLogs, "5️⃣ 日志探针"),
        (TestSessionCRUD, "6️⃣ 会话管理 CRUD"),
        (TestChatEndpoint, "7️⃣ AI 对话"),
        (TestSafetyValidator, "8️⃣ 命令安全校验"),
        (TestSafetyExecute, "9️⃣ 安全执行"),
        (TestSafetyStatus, "🔟 安全层总览"),
        (TestPromptInjection, "1️⃣1️⃣ 提示词注入防护"),
        (TestConfigGuard, "1️⃣2️⃣ 配置写保护"),
        (TestConfigManagement, "1️⃣3️⃣ 系统配置管理"),
        (TestToolManagement, "1️⃣4️⃣ 动态工具管理"),
        (TestAuditLogs, "1️⃣5️⃣ 审计日志"),
        (TestReasoningChain, "1️⃣6️⃣ 推理链路"),
    ]

    total_start = time.monotonic()
    for cls, name in suites:
        await runner.run_class(cls, name)
    total_elapsed = (time.monotonic() - total_start) * 1000

    all_passed = runner.print_report()
    print(f"  总用时: {total_elapsed:.0f}ms\n")
    return all_passed


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    start_dt = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[START] {start_dt}")
    print(f"  🚀 DevOps Agent 交付测试")
    print(f"  目标地址: {base_url}")

    total_start = time.monotonic()
    ok = asyncio.run(main(base_url))
    total_elapsed = (time.monotonic() - total_start) * 1000

    end_dt = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[END]   {end_dt}")
    print(f"[TOTAL] {total_elapsed:.0f}ms")
    print(f"[RESULT] {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)
