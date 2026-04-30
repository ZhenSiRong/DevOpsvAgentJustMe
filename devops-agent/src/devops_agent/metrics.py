"""可观测性 Metrics 端点

提供 Prometheus-text 格式的 /metrics 端点，暴露以下指标：

计数器（Counter）：
- devops_agent_requests_total{endpoint, method, status}
- devops_agent_llm_calls_total{protocol}
- devops_agent_tool_calls_total{tool_name}
- devops_agent_commands_executed_total{status}
- devops_agent_security_blocks_total

直方图（Histogram）：
- devops_agent_request_duration_seconds
- devops_agent_llm_call_duration_seconds

仪表盘（Gauge）：
- devops_agent_active_sessions
"""

from __future__ import annotations

import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


# ============================================================
#  内存指标存储（线程安全仅限 asyncio 单线程模型）
# ============================================================

_counters: dict[str, int] = defaultdict(int)
_histograms: dict[str, list[float]] = defaultdict(list)
_gauges: dict[str, float] = defaultdict(float)

_start_time = time.time()


# ============================================================
#  指标记录 API（供各模块调用）
# ============================================================

def inc_counter(name: str, value: int = 1, labels: dict[str, str] | None = None) -> None:
    """计数器 +1"""
    key = _with_labels(name, labels)
    _counters[key] += value


def observe_histogram(name: str, seconds: float, labels: dict[str, str] | None = None) -> None:
    """记录直方图观测值（保留最近 1000 条）"""
    key = _with_labels(name, labels)
    hist = _histograms[key]
    hist.append(seconds)
    if len(hist) > 1000:
        _histograms[key] = hist[-1000:]


def set_gauge(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    """设置仪表盘值"""
    key = _with_labels(name, labels)
    _gauges[key] = value


# ============================================================
#  Prometheus text 格式输出
# ============================================================

def _with_labels(name: str, labels: dict[str, str] | None) -> str:
    if not labels:
        return name
    label_pairs = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return f"{name}{{{label_pairs}}}"


def render_metrics() -> str:
    """生成 Prometheus text 格式的 metrics 输出"""
    lines = [
        "# HELP devops_agent_uptime_seconds Agent 进程运行时间",
        "# TYPE devops_agent_uptime_seconds gauge",
        f"devops_agent_uptime_seconds {time.time() - _start_time:.2f}",
        "",
    ]

    for key, value in sorted(_counters.items()):
        name = key.split("{")[0] if "{" in key else key
        lines.append(f"# HELP {name} 计数器")
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{key} {value}")
        lines.append("")

    for key, values in sorted(_histograms.items()):
        name = key.split("{")[0] if "{" in key else key
        if not values:
            continue
        sorted_vals = sorted(values)
        count = len(sorted_vals)
        total = sum(sorted_vals)
        avg = total / count if count else 0
        p50 = sorted_vals[count // 2]
        p90 = sorted_vals[int(count * 0.9)] if count > 1 else sorted_vals[0]
        p99 = sorted_vals[int(count * 0.99)] if count > 1 else sorted_vals[0]

        lines.append(f"# HELP {name} 耗时直方图（秒）")
        lines.append(f"# TYPE {name} summary")
        lines.append(f"{name}_count{_label_suffix(key)} {count}")
        lines.append(f"{name}_sum{_label_suffix(key)} {total:.6f}")
        lines.append(f"{name}_avg{_label_suffix(key)} {avg:.6f}")
        lines.append(f"{name}_p50{_label_suffix(key)} {p50:.6f}")
        lines.append(f"{name}_p90{_label_suffix(key)} {p90:.6f}")
        lines.append(f"{name}_p99{_label_suffix(key)} {p99:.6f}")
        lines.append("")

    for key, value in sorted(_gauges.items()):
        name = key.split("{")[0] if "{" in key else key
        lines.append(f"# HELP {name} 仪表盘")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{key} {value}")
        lines.append("")

    return "\n".join(lines)


def _label_suffix(key: str) -> str:
    """提取 key 中的 labels 部分（{...}）"""
    idx = key.find("{")
    return key[idx:] if idx >= 0 else ""


# ============================================================
#  便捷包装（供 Agent Core / 路由使用）
# ============================================================

class RequestMetrics:
    """请求级指标追踪"""

    __slots__ = ("endpoint", "method", "start")

    def __init__(self, endpoint: str, method: str) -> None:
        self.endpoint = endpoint
        self.method = method
        self.start = time.monotonic()

    def done(self, status: int) -> None:
        elapsed = time.monotonic() - self.start
        inc_counter("devops_agent_requests_total", labels={
            "endpoint": self.endpoint, "method": self.method, "status": str(status),
        })
        observe_histogram("devops_agent_request_duration_seconds", elapsed)


def record_llm_call(protocol: str, duration: float) -> None:
    """记录一次 LLM 调用"""
    inc_counter("devops_agent_llm_calls_total", labels={"protocol": protocol})
    observe_histogram("devops_agent_llm_call_duration_seconds", duration)


def record_tool_call(tool_name: str, duration: float) -> None:
    """记录一次工具调用"""
    inc_counter("devops_agent_tool_calls_total", labels={"tool_name": tool_name})
    observe_histogram("devops_agent_tool_call_duration_seconds", duration)


def record_command_executed(status: str) -> None:
    """记录一次命令执行"""
    inc_counter("devops_agent_commands_executed_total", labels={"status": status})


def record_security_block() -> None:
    """记录一次安全拦截"""
    inc_counter("devops_agent_security_blocks_total")


__all__ = [
    "render_metrics",
    "inc_counter",
    "observe_histogram",
    "set_gauge",
    "RequestMetrics",
    "record_llm_call",
    "record_tool_call",
    "record_command_executed",
    "record_security_block",
]
