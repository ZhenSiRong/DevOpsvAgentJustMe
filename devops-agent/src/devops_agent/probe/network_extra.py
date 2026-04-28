"""
网络诊断扩展探针 — ping、路由追踪、HTTP探测、socket详情。

提供的接口：
- ping_host(host, count)      → 连通性测试
- trace_route(host)           → 路由追踪
- http_probe(url)             → HTTP 探测
- socket_list()               → Socket 统计（ss/netstat增强版）
"""

from __future__ import annotations

import re
from typing import Any

from .base import (
    ProbeResult,
    ProbeStatus,
    _run_command,
    _make_result,
)


async def ping_host(host: str, count: int = 4, timeout: float = 15.0) -> ProbeResult:
    """
    对目标主机执行 ping 连通性测试。

    Args:
        host: 目标主机名或 IP
        count: 发送包数（默认 4）
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 dict：
        - host / transmitted / received / loss_percent / time_ms
        - min_rtt / avg_rtt / max_rtt / mdev_rtt
    """
    probe_name = "ping_host"
    stdout, rc, err = await _run_command(
        "ping", "-c", str(count), "-W", "2", host, timeout=timeout
    )

    # ping 返回码 1 表示全部丢包（不是命令错误）
    if rc not in (0, 1) or stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    data = _parse_ping_output(stdout, host)
    return _make_result(probe_name, ProbeStatus.SUCCESS, data=data)


async def trace_route(host: str, timeout: float = 30.0) -> ProbeResult:
    """
    路由追踪。

    使用 `traceroute -n`。

    Args:
        host: 目标主机名或 IP
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - hop / ip / rtt1 / rtt2 / rtt3
    """
    probe_name = "trace_route"
    stdout, rc, err = await _run_command(
        "traceroute", "-n", "-q", "1", "-w", "2", host, timeout=timeout
    )

    if rc != 0 or stdout is None:
        # traceroute 可能部分失败但仍有输出
        if not stdout:
            return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    hops = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("traceroute"):
            continue

        # traceroute -n 格式：
        #  1  192.168.1.1  1.234 ms
        #  2  * * *
        #  3  10.0.0.1  2.1 ms  2.2 ms  2.3 ms
        hop_match = re.match(r"\s*(\d+)\s+(.+)", line)
        if not hop_match:
            continue

        hop_num = hop_match.group(1)
        rest = hop_match.group(2)

        if rest.startswith("*"):
            hops.append({
                "hop": int(hop_num),
                "ip": None,
                "rtt_ms": None,
                "status": "timeout",
            })
        else:
            parts = rest.split()
            ip = parts[0] if parts else None
            # 提取第一个 RTT
            rtt = None
            for p in parts[1:]:
                rtt_match = re.match(r"([\d.]+)\s*ms", p)
                if rtt_match:
                    rtt = float(rtt_match.group(1))
                    break

            hops.append({
                "hop": int(hop_num),
                "ip": ip,
                "rtt_ms": rtt,
                "status": "ok",
            })

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=hops)


async def http_probe(url: str, timeout: float = 10.0) -> ProbeResult:
    """
    HTTP 探测。

    使用 `curl -I -s -o /dev/null -w` 获取状态码和响应时间。

    Args:
        url: 目标 URL
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 dict：
        - url / status_code / response_time_ms / content_type / server
    """
    probe_name = "http_probe"

    fmt = "\\nHTTP_CODE:%{http_code}\\nTIME_TOTAL:%{time_total}\\nSIZE_DOWNLOAD:%{size_download}\\nCONTENT_TYPE:%{content_type}\\n"
    stdout, rc, err = await _run_command(
        "curl", "-s", "-o", "/dev/null", "-I", "-w", fmt,
        "--max-time", str(timeout), "--connect-timeout", "5",
        url, timeout=timeout + 5,
    )

    if rc != 0 or stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    data = {
        "url": url,
        "status_code": None,
        "response_time_ms": None,
        "size_download": None,
        "content_type": None,
    }

    for line in stdout.strip().split("\n"):
        line = line.strip()
        if line.startswith("HTTP_CODE:"):
            code_str = line.split(":", 1)[1].strip()
            try:
                data["status_code"] = int(code_str)
            except ValueError:
                data["status_code"] = code_str
        elif line.startswith("TIME_TOTAL:"):
            try:
                data["response_time_ms"] = round(float(line.split(":", 1)[1].strip()) * 1000, 2)
            except ValueError:
                pass
        elif line.startswith("SIZE_DOWNLOAD:"):
            try:
                data["size_download"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("CONTENT_TYPE:"):
            data["content_type"] = line.split(":", 1)[1].strip()

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=data)


async def socket_list(protocol: str | None = None, state: str | None = None, timeout: float = 10.0) -> ProbeResult:
    """
    获取 Socket 统计（ss 命令增强版）。

    与 network_connections 类似，但提供更完整的连接信息，
    包括进程名、接收/发送队列等。

    Args:
        protocol: 可选过滤 ("tcp" / "udp" / "unix")
        state: 可选过滤 ("ESTAB" / "LISTEN" / "TIME-WAIT" 等)
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]
    """
    probe_name = "socket_list"

    # ss -tnp 或 ss -unp 等
    proto_flag = "-t" if protocol == "tcp" else "-u" if protocol == "udp" else "-x" if protocol == "unix" else "-t"
    stdout, rc, err = await _run_command("ss", proto_flag, "-np", timeout=timeout)

    if rc != 0 or stdout is None:
        # 回退 netstat
        netstat_proto = "-t" if protocol == "tcp" else "-u" if protocol == "udp" else "-t"
        stdout, rc, err = await _run_command("netstat", netstat_proto, "-np", timeout=timeout)

    if rc != 0 or stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    connections = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("State") or line.startswith("Proto"):
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        conn_state = parts[0]
        if state and conn_state.upper() != state.upper():
            continue

        recv_q = send_q = "0"
        local_addr = remote_addr = ""
        process_info = ""

        # ss -tnp 格式：State Recv-Q Send-Q Local Address:Port Peer Address:Port Process
        if len(parts) >= 6:
            recv_q = parts[1]
            send_q = parts[2]
            local_addr = parts[3]
            remote_addr = parts[4]
            process_info = parts[5] if len(parts) > 5 else ""
        else:
            local_addr = parts[3] if len(parts) > 3 else ""
            remote_addr = parts[4] if len(parts) > 4 else ""

        connections.append({
            "state": conn_state,
            "recv_q": recv_q,
            "send_q": send_q,
            "local_address": local_addr,
            "remote_address": remote_addr,
            "process": process_info,
        })

    return _make_result(probe_name, ProbeStatus.SUCCESS, data=connections)


# ============================================================
#  内部解析函数
# ============================================================

def _parse_ping_output(stdout: str, host: str) -> dict[str, Any]:
    """解析 ping 命令输出。"""
    data = {
        "host": host,
        "transmitted": 0,
        "received": 0,
        "loss_percent": 100.0,
        "time_ms": None,
        "min_rtt": None,
        "avg_rtt": None,
        "max_rtt": None,
        "mdev_rtt": None,
    }

    # 解析统计行（支持中英文）：
    # 英文: 4 packets transmitted, 4 received, 0% packet loss
    # 中文: 已发送 2 个包， 已接收 2 个包, 0% packet loss
    stats_match = re.search(
        r"(\d+)\s+(?:packets? transmitted|个包[^,]*发送)\s*[，,]?\s*(?:\d+\s+个包)?\s*[，,]?\s*(\d+)\s+(?:received|个包[^,]*接收)\s*[，,]?\s*([\d.]+)%\s+packet loss",
        stdout,
    )
    if not stats_match:
        # 更宽松的中文匹配
        stats_match = re.search(
            r"(?:已发送|发送)\s*(\d+)\s*[^,]*\s*[，,]?\s*(?:已接收|接收)\s*(\d+)\s*[^,]*\s*[，,]?\s*([\d.]+)%",
            stdout,
        )
    if stats_match:
        data["transmitted"] = int(stats_match.group(1))
        data["received"] = int(stats_match.group(2))
        data["loss_percent"] = float(stats_match.group(3))

    time_match = re.search(r"time\s+(\d+)ms", stdout)
    if time_match:
        data["time_ms"] = int(time_match.group(1))

    # 解析 RTT 行：rtt min/avg/max/mdev = 1.234/2.345/3.456/0.123 ms
    rtt_match = re.search(
        r"rtt\s+min/avg/max/mdev\s+=\s+([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s+ms",
        stdout,
    )
    if rtt_match:
        data["min_rtt"] = float(rtt_match.group(1))
        data["avg_rtt"] = float(rtt_match.group(2))
        data["max_rtt"] = float(rtt_match.group(3))
        data["mdev_rtt"] = float(rtt_match.group(4))

    return data


__all__ = [
    "ping_host",
    "trace_route",
    "http_probe",
    "socket_list",
]
