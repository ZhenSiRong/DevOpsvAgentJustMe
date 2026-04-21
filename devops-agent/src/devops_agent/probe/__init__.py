"""探针子系统 — Agent 感知 OS 环境的只读通道"""

from .disk import disk_usage, large_files
from .process import process_list, process_detail
from .network import network_connections, network_interfaces, dns_resolve
from .logs import journal_logs, tail_file, grep_log

__all__ = [
    # 磁盘探针
    "disk_usage",
    "large_files",
    # 进程探针
    "process_list",
    "process_detail",
    # 网络探针
    "network_connections",
    "network_interfaces",
    "dns_resolve",
    # 日志探针
    "journal_logs",
    "tail_file",
    "grep_log",
]
