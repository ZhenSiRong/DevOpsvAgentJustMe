"""探针子系统 — Agent 感知 OS 环境的只读通道"""

from .disk import disk_usage, large_files
from .process import process_list, process_detail
from .network import network_connections, network_interfaces, dns_resolve
from .logs import journal_logs, tail_file, grep_log
from .system import system_top, memory_usage, system_uptime, system_vmstat
from .filesystem import (
    directory_size, disk_iostat, block_devices,
    list_directory, find_files, file_stat, file_type, read_file,
)
from .service import service_status, service_list
from .network_extra import ping_host, trace_route, http_probe, socket_list
from .process_extra import process_find, process_tree, list_open_files
from .logs_extra import kernel_messages, log_slice
from .security import selinux_status, failed_logins
from .hardware import cpu_info, memory_info, pci_devices

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
    # 系统监控探针
    "system_top",
    "memory_usage",
    "system_uptime",
    "system_vmstat",
    # 文件系统探针
    "directory_size",
    "disk_iostat",
    "block_devices",
    "list_directory",
    "find_files",
    "file_stat",
    "file_type",
    "read_file",
    # 服务管理探针
    "service_status",
    "service_list",
    # 网络诊断扩展探针
    "ping_host",
    "trace_route",
    "http_probe",
    "socket_list",
    # 进程管理扩展探针
    "process_find",
    "process_tree",
    "list_open_files",
    # 日志分析扩展探针
    "kernel_messages",
    "log_slice",
    # 安全审计探针
    "selinux_status",
    "failed_logins",
    # 硬件信息探针
    "cpu_info",
    "memory_info",
    "pci_devices",
]
