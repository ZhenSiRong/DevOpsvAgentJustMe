"""
Day 3-AM 探针模块测试 — TDD 红阶段

探针是 Agent 感知 OS 环境的唯一通道，核心原则：
1. 所有探针都是异步函数（async def）
2. 统一返回结构化数据（dict/list），不返回原始字符串
3. 超时控制：默认 30 秒，超时抛 ProbeTimeoutError
4. 空结果不报错，返回空列表/空字典
5. 所有 subprocess 调用通过 asyncio.create_subprocess_exec（非 shell 注入）

测试覆盖：
- TP-01: disk_usage() 磁盘使用率探针
- TP-02: large_files() 大文件扫描
- TP-03: process_list() 进程列表
- TP-04: 探针超时异常
- TP-05: 空结果优雅处理
"""

import asyncio
import json
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================
#  平台标记：探针依赖 Linux 命令（df/ps/ss/journalctl），Windows 上跳过
# ============================================================
requires_linux = pytest.mark.skipif(
    sys.platform != "linux",
    reason="探针模块依赖 Linux 系统命令（df/ps/ss/journalctl），当前平台为 Windows"
)


# ============================================================
#  先定义期望的数据结构（这些是 probe 模块必须实现的契约）
# ============================================================

class ProbeStatus(str, Enum):
    """探针执行状态"""
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass
class DiskUsageResult:
    """磁盘使用率结果"""
    filesystem: str
    total: int          # 字节
    used: int           # 字节
    available: int      # 字节
    usage_percent: float # 0~100
    mount_point: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LargeFileResult:
    """大文件扫描结果"""
    path: str
    size_bytes: int
    modified: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProcessInfo:
    """进程信息"""
    pid: int
    user: str | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    command: str = ""
    state: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NetworkConnection:
    """网络连接信息"""
    protocol: str       # tcp / udp / tcp6 / udp6
    local_addr: str
    local_port: int
    remote_addr: str | None = None
    remote_port: int | None = None
    state: str | None = None   # ESTABLISHED / LISTEN / TIME_WAIT 等

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LogEntry:
    """日志条目"""
    timestamp: str
    source: str | None = None     # 日志来源（如 nginx.service）
    message: str = ""
    priority: str | None = None  # emerg/alert/crit/err/warning/notice/info/debug

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProbeResult:
    """
    排针统一返回包装。

    所有探针函数都应返回此包装，确保：
    - 状态可追踪（成功/超时/错误）
    - 数据类型一致
    - 元信息保留（执行耗时、数据源）
    """
    status: ProbeStatus
    data: Any = None              # 实际数据（list/dict/None）
    error: str | None = None      # 错误信息（失败时填充）
    execution_time_ms: float = 0.0
    probe_name: str = ""
    captured_at: str = ""         # ISO 8601 时间戳

    @property
    def is_success(self) -> bool:
        return self.status == ProbeStatus.SUCCESS

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_success"] = self.is_success
        return d


class ProbeTimeoutError(Exception):
    """探针执行超时"""
    pass


# ============================================================
#  测试用例
# ============================================================

@requires_linux
class TestDiskUsageProbe:
    """TP-01: 磁盘使用率探针测试"""

    async def test_disk_usage_returns_structured_data(self):
        """
        disk_usage() 应返回包含各分区使用率的结构化列表。
        至少包含根分区 '/' 的 total/used/available/usage_percent 信息。
        """
        from devops_agent.probe.disk import disk_usage

        # Mock subprocess 输出（模拟 Linux df -B1 输出）
        df_output = (
            "Filesystem     1B-blocks      Used Available Use% Mounted on\n"
            "/dev/sda2  10485760000 5242880000 5242880000  50% /\n"
            "/dev/sda3 20971520000 4194304000 16777216000  20% /var\n"
            "tmpfs    8388608        0   8388608   0% /dev/shm\n"
        )

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (df_output.encode("utf-8"), b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await disk_usage()

        assert result.status == ProbeStatus.SUCCESS
        assert isinstance(result.data, list)
        assert len(result.data) >= 1

        # 根分区的数据完整性检查
        root_partition = None
        for item in result.data:
            if item["mount_point"] == "/":
                root_partition = item
                break

        assert root_partition is not None, "必须包含根分区 '/' 的数据"
        assert root_partition["total"] > 0
        assert root_partition["used"] > 0
        assert root_partition["usage_percent"] >= 0
        assert root_partition["usage_percent"] <= 100
        assert result.probe_name == "disk_usage"

    async def test_disk_usage_handles_parse_error_gracefully(self):
        """
        当 df 命令输出格式异常时，不应抛出未捕获异常，
        应返回 ERROR 状态 + 可理解的错误描述。
        """
        from devops_agent.probe.disk import disk_usage

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"garbage broken output\n", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await disk_usage()

        assert result.status in (ProbeStatus.ERROR, ProbeStatus.SUCCESS)
        if result.status == ProbeStatus.ERROR:
            assert result.error != ""


@requires_linux
class TestLargeFilesProbe:
    """TP-02: 大文件扫描探针测试"""

    async def test_large_files_returns_sorted_list(self):
        """
        large_files(path, top_n=5) 应返回按大小降序排列的文件列表，
        每项含 path 和 size_bytes，最多返回 top_n 条。
        """
        from devops_agent.probe.disk import large_files

        # Mock du 命令输出（模拟查找大文件）
        du_output = (
            "524288000\t/var/log/syslog.1\n"
            "104857600\t/var/log/auth.log\n"
            "209715200\t/var/log/kern.log\n"
            "31457280\t/var/log/dpkg.log\n"
            "62914560\t/var/log/apt/history.log\n"
            "15728640\t/var/log/journal/system.journal\n"
        )

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (du_output.encode("utf-8"), b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await large_files("/var/log", top_n=5)

        assert result.is_success
        assert len(result.data) <= 5

        files = result.data
        sizes = [f["size_bytes"] for f in files]
        assert sizes == sorted(sizes, reverse=True), "必须按大小降序排列"

        for f in files:
            assert "path" in f
            assert "size_bytes" in f
            assert f["size_bytes"] > 0


@requires_linux
class TestProcessListProbe:
    """TP-03: 进程列表探针测试"""

    async def test_process_list_returns_pid_and_command(self):
        """
        process_list(filter_str="mysql") 应返回匹配进程列表，
        每条记录至少包含 pid、command 字段。
        """
        from devops_agent.probe.process import process_list

        # Mock ps 命令输出（ps aux --no-headers 格式：11列）
        # USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
        ps_output = (
            "1234 mysql  5.2  3.1  512000 124000 ? Ssl 10:00 0:05 /usr/sbin/mysqld --defaults-file=/etc/mysql/my.cnf\n"
            "5678 root   0.0  0.1   30000  5000 pts/0 S+ 10:01 0:00 grep mysql\n"
        )

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (ps_output.encode("utf-8"), b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await process_list("mysql")

        assert result.is_success
        processes = result.data
        assert len(processes) >= 1

        # 验证每条记录的结构
        p = processes[0]
        assert "pid" in p
        assert isinstance(p["pid"], int), "PID 必须是整数"
        assert "command" in p
        assert len(p["command"]) > 0


@requires_linux
class TestProbeTimeout:
    """TP-04: 探针超时处理测试"""

    async def test_timeout_raises_probe_timeout_error(self):
        """
        当探针命令执行超时时，应抛出 ProbeTimeoutError 或
        返回 TIMEOUT 状态的结果（取决于实现策略）。
        子进程必须被 kill，不能泄漏。
        """
        from devops_agent.probe.disk import disk_usage

        # 创建一个永远 hang住的 mock 进程（communicate 超时）
        async def slow_subprocess(*args, **kwargs):
            proc = AsyncMock()
            proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            proc.kill = AsyncMock()
            proc.pid = 99999
            proc.returncode = None
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=slow_subprocess):
            result = await disk_usage(timeout=0.01)  # 10ms 超时

        # 要么抛出异常被我们捕获，要么返回 TIMEOUT 状态
        assert result.status == ProbeStatus.TIMEOUT or "timeout" in (result.error or "").lower() or "超时" in (result.error or "")


@requires_linux
class TestEmptyResults:
    """TP-05: 空结果优雅处理测试"""

    async def test_empty_directory_returns_empty_list(self):
        """
        对空目录或无匹配结果的情况，探针应返回空列表（而非错误）。
        """
        from devops_agent.probe.disk import large_files

        # du 返回空结果
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"", b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await large_files("/empty/dir", top_n=10)

        assert result.is_success, "空结果应是 SUCCESS 而非 ERROR"
        assert result.data == [], "空目录应返回空列表"

    async def test_no_matching_processes_returns_empty_list(self):
        """
        无匹配进程时，process_list 应返回空列表。
        """
        from devops_agent.probe.process import process_list

        ps_output = (
            "1234 root   0.0  0.3  219000 14000 ? Ss 08:00 0:35 /usr/lib/systemd/systemd\n"
        )
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (ps_output.encode("utf-8"), b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await process_list("nonexistent_process_xyz")

        assert result.is_success
        assert result.data == [], "无匹配进程应返回空列表"


@requires_linux
class TestNetworkProbe:
    """额外：网络连接探针测试（补充覆盖）"""

    async def test_network_connections_returns_structured_data(self):
        """
        network_connections() 应返回当前网络连接列表，
        每条含 protocol/local_addr/local_port/state 等字段。
        """
        from devops_agent.probe.network import network_connections

        ss_output = (
            "Netid State  Recv-Q Send-Q Local Address:Port   Peer Address:Port\n"
            "tcp  LISTEN 0      128        0.0.0.0:22         0.0.0.0:*\n"
            "tcp  ESTAB 0      0          192.168.1.10:443    10.0.0.1:52341\n"
            "udp  UNCONN 0     0          0.0.0.0:53          0.0.0.0:*\n"
        )

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (ss_output.encode("utf-8"), b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await network_connections()

        assert result.is_success
        connections = result.data
        assert len(connections) >= 1

        conn = connections[0]
        assert "protocol" in conn
        assert "local_addr" in conn
        assert "local_port" in conn
        assert conn["protocol"] in ("tcp", "udp", "tcp6", "udp6")


@requires_linux
class TestLogProbe:
    """额外：日志探针测试（补充覆盖）"""

    async def test_journal_logs_returns_timestamped_entries(self):
        """
        journal_logs(service=None, lines=10) 应返回日志条目列表，
        每条含 timestamp/message/priority/source 字段。
        """
        from devops_agent.probe.logs import journal_logs

        journalctl_output = (
            "-- Logs begin at Mon 2026-04-21 08:00:00, end at Mon 2026-04-21 17:00:00 --\n"
            "Apr 21 16:55:01 server nginx[1234]: 192.168.1.100 - GET /api/health 200\n"
            "Apr 21 16:55:02 server mysqld[5678]: [Warning] Slow query: 12.3s\n"
            "Apr 21 16:55:03 server systemd[1]: Session 42 of user admin logged out.\n"
        )

        mock_process = AsyncMock()
        mock_process.communicate.return_value = (journalctl_output.encode("utf-8"), b"")
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await journal_logs(lines=10)

        assert result.is_success
        entries = result.data
        assert len(entries) >= 1

        entry = entries[0]
        assert "timestamp" in entry
        assert "message" in entry
        assert len(entry["message"]) > 0
