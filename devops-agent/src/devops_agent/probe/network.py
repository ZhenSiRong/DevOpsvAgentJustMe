"""
网络探针模块 — 感知系统网络连接状态。

提供的接口：
- network_connections()     → 当前活跃的网络连接列表
- network_interfaces()      → 网络接口信息（IP/MAC/状态）
- dns_resolve(hostname)     → DNS 解析
"""

from __future__ import annotations

import re

from .base import (
    NetworkConnection,
    ProbeResult,
    ProbeStatus,
    _run_command,
    _make_result,
)


async def network_connections(
    protocol: str | None = None,
    state: str | None = None,
    timeout: float = 30.0,
) -> ProbeResult:
    """
    获取当前系统的网络连接列表。

    使用 `ss -tnp`（或回退到 `netstat -tln`）获取 TCP/UDP 连接。

    Args:
        protocol: 可选过滤 ("tcp" / "udp")，不过滤则返回全部
        state: 可选过滤 ("ESTABLISHED" / "LISTEN" / "TIME_WAIT" 等)
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - protocol / local_addr / local_port / remote_addr / remote_port / state
    """
    probe_name = "network_connections"

    # 优先使用 ss（iproute2），回退 netstat
    stdout, rc, err = await _run_command("ss", "-tn", timeout=timeout)

    if rc != 0:
        # 回退到 netstat
        stdout, rc, err = await _run_command("netstat", "-tn", timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    connections = []
    lines = stdout.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line or line.startswith("State") or line.startswith("Proto"):
            continue  # 跳过表头和空行

        conn = _parse_ss_line(line)
        if conn is None:
            continue

        # 应用过滤器
        if protocol and conn.protocol != protocol.lower():
            continue
        if state and (conn.state or "").upper() != state.upper():
            continue

        connections.append(conn.to_dict())

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=connections,
    )


async def network_interfaces(timeout: float = 10.0) -> ProbeResult:
    """
    获取所有网络接口的 IP 地址和状态。

    使用 `ip -o addr show` 获取结构化输出。

    Returns:
        ProbeResult.data 为 list[dict]，每项含：
        - name: 接口名（eth0/lo 等）
        - ip_addr: IPv4 地址
        - mac_addr: MAC 地址（如果有）
        - state: UP / DOWN / UNKNOWN
    """
    probe_name = "network_interfaces"

    stdout, rc, err = await _run_command("ip", "-o", "addr", "show", timeout=timeout)

    if rc != 0:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    if stdout is None:
        return _make_result(probe_name, ProbeStatus.ERROR, error=err)

    interfaces = {}
    lines = stdout.strip().split("\n")

    current_if = None
    for line in lines:
        # ip -o addr show 输出格式：
        # 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 ...
        #     inet 127.0.0.1/8 scope host lo \n...
        # 2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ...

        if re.match(r"^\d+:\s+\S+", line):
            # 新接口行
            match = re.match(r"^\d+:\s+(\w+)\s+(?:<(\w+)>)?.*?", line)
            if match:
                current_if = match.group(1)
                state_str = match.group(2) or ""
                interfaces[current_if] = {
                    "name": current_if,
                    "ip_addr": "",
                    "mac_addr": "",
                    "state": "UP" if "UP" in state_str else "DOWN",
                }
        elif current_if and "inet " in line:
            # IP 地址行：inet 192.168.1.100/24 brd ...
            match = re.search(r"inet\s+(\S+)", line)
            if match:
                interfaces[current_if]["ip_addr"] = match.group(1).split("/")[0]

        elif current_if and "link/ether" in line:
            # MAC 地址行：link/ether aa:bb:cc:dd:ee:ff
            match = re.search(r"link/ether\s+(\S+)", line)
            if match:
                interfaces[current_if]["mac_addr"] = match.group(1)

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS,
        data=list(interfaces.values()),
    )


async def dns_resolve(hostname: str, timeout: float = 5.0) -> ProbeResult:
    """
    DNS 解析测试。

    使用 `dig +short` 或 `getent hosts` 解析域名。

    Args:
        hostname: 要解析的主机名
        timeout: 超时时间（秒）

    Returns:
        ProbeResult.data 为 dict：{"hostname": ..., "resolved_ips": [...], "resolve_time_ms": ...}
    """
    probe_name = "dns_resolve"
    import time

    start_time = time.monotonic()
    stdout, rc, err = await _run_command("getent", "hosts", hostname, timeout=timeout)
    elapsed = (time.monotonic() - start_time) * 1000

    resolved_ips = []

    if rc == 0 and stdout:
        for line in stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 1:
                resolved_ips.append(parts[0])

    return _make_result(
        probe_name,
        ProbeStatus.SUCCESS if resolved_ips else ProbeStatus.ERROR,
        data={
            "hostname": hostname,
            "resolved_ips": resolved_ips,
            "resolve_time_ms": round(elapsed, 2),
        },
        error=None if resolved_ips else f"无法解析主机名: {hostname}",
    )


# ============================================================
#  内部解析函数
# ============================================================

def _parse_ss_line(line: str) -> NetworkConnection | None:
    """
    解析 ss -tn 输出的单行。
    ss 格式示例：
    State   Recv-Q Send-Q  Local Address:Port   Peer Address:Port Process
    ESTAB   0      0       192.168.1.10:443      10.0.0.1:52341
    LISTEN  0      128     0.0.0.0:22             0.0.0.0:*
    """
    # ss -tn 无表头时，格式为：
    # ESTAB  0 0 192.168.1.10:443 10.0.0.1:52341
    parts = line.split()
    if len(parts) < 5:
        return None

    state = parts[0]
    local_parts = _split_addr_port(parts[3])
    remote_parts = _split_addr_port(parts[4]) if len(parts) > 4 else (None, None)

    # 判断协议：如果地址包含冒号则是 IPv6（tcp6），否则 tcp
    local_addr_raw = parts[3] if len(parts) > 3 else ""
    proto = "tcp6" if local_addr_raw.count(":") > 1 else "tcp"

    return NetworkConnection(
        protocol=proto,
        local_addr=local_parts[0],
        local_port=local_parts[1],
        remote_addr=remote_parts[0],
        remote_port=remote_parts[1],
        state=state,
    )


def _split_addr_port(addr_port: str) -> tuple[str | None, int]:
    """
    从 "addr:port" 字符串中拆分出地址和端口。
    支持 IPv4 (192.168.1.1:8080) 和 IPv6 ([::1]:8080)。
    """
    if not addr_port:
        return (None, 0)

    # IPv6 地址带方括号：[::1]:8080
    if addr_port.startswith("["):
        bracket_end = addr_port.find("]")
        if bracket_end < 0:
            return (None, 0)
        addr = addr_port[1:bracket_end]
        rest = addr_port[bracket_end + 1:]  # :8080
        port_str = rest.lstrip(":")
        port = int(port_str) if port_str.isdigit() else 0
        return (addr, port)

    # IPv4 地址：192.168.1.1:8080
    last_colon = addr_port.rfind(":")
    if last_colon < 0:
        return (addr_port, 0)

    addr = addr_port[:last_colon]
    port_str = addr_port[last_colon + 1:]
    port = int(port_str) if port_str.isdigit() else 0

    # 处理 * 通配符
    if addr == "*" or addr == "0.0.0.0":
        addr = "0.0.0.0"

    return (addr, port)


__all__ = [
    "network_connections",
    "network_interfaces",
    "dns_resolve",
]
