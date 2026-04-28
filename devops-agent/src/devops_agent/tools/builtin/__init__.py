"""
内置 MCP 工具包 —— 自动注册所有内置工具

导入此模块时，会自动创建各工具实例并注册到 ToolRegistry。
Agent 核心引擎只需导入此模块即可使所有内置工具生效。

当前内置工具（38 个）：

【系统监控】
- disk_usage              磁盘使用
- large_files             大文件扫描
- system_top              CPU/内存最高进程
- memory_usage            内存用量
- system_uptime           系统负载与运行时长
- system_vmstat           系统整体状态采样

【进程管理】
- process_list            进程列表
- process_detail          进程详情
- process_find            按名查找 PID
- process_tree            进程树
- list_open_files         打开文件/端口（lsof）

【网络诊断】
- network_connections     网络连接
- network_interfaces      网络接口
- dns_resolve             DNS 解析
- ping_host               Ping 连通性测试
- trace_route             路由追踪
- http_probe              HTTP 探测
- socket_list             Socket 统计（ss）

【日志分析】
- query_logs              系统日志查询（journalctl）
- tail_file               文件尾读取
- kernel_messages         内核日志（dmesg）
- log_slice               日志行号范围提取

【文件系统】
- directory_size          目录大小
- disk_iostat             磁盘 IO 统计
- block_devices           块设备信息
- list_directory          列出目录
- find_files              文件搜索
- file_stat               文件元信息
- file_type               文件类型检测
- read_file               读取文件内容

【服务管理】
- service_status          服务状态
- service_list            服务列表

【安全审计】
- selinux_status          SELinux 状态
- failed_logins           失败登录记录

【硬件信息】
- cpu_info                CPU 信息
- memory_info             内存硬件信息
- pci_devices             PCI 设备列表

【执行器】
- execute_command         安全命令执行（受安全层约束）
"""

from .disk import DiskUsageTool, LargeFilesTool
from .process import ProcessListTool, ProcessDetailTool
from .network import NetworkConnectionsTool, NetworkInterfacesTool, DNSResolveTool
from .logs import QueryLogsTool, TailFileTool
from .executor import ExecuteCommandTool
from .system import (
    SystemTopTool, MemoryUsageTool, SystemUptimeTool, SystemVmstatTool,
)
from .filesystem import (
    DirectorySizeTool, DiskIostatTool, BlockDevicesTool,
    ListDirectoryTool, FindFilesTool, FileStatTool, FileTypeTool, ReadFileTool,
)
from .service import ServiceStatusTool, ServiceListTool
from .network_extra import PingHostTool, TraceRouteTool, HttpProbeTool, SocketListTool
from .process_extra import ProcessFindTool, ProcessTreeTool, ListOpenFilesTool
from .logs_extra import KernelMessagesTool, LogSliceTool
from .security import SELinuxStatusTool, FailedLoginsTool
from .hardware import CPUInfoTool, MemoryInfoTool, PCIDevicesTool

__all__ = [
    # 原有 10 个
    "DiskUsageTool", "LargeFilesTool",
    "ProcessListTool", "ProcessDetailTool",
    "NetworkConnectionsTool", "NetworkInterfacesTool", "DNSResolveTool",
    "QueryLogsTool", "TailFileTool",
    "ExecuteCommandTool",
    # 系统监控 4 个
    "SystemTopTool", "MemoryUsageTool", "SystemUptimeTool", "SystemVmstatTool",
    # 文件系统 8 个
    "DirectorySizeTool", "DiskIostatTool", "BlockDevicesTool",
    "ListDirectoryTool", "FindFilesTool", "FileStatTool", "FileTypeTool", "ReadFileTool",
    # 服务管理 2 个
    "ServiceStatusTool", "ServiceListTool",
    # 网络扩展 4 个
    "PingHostTool", "TraceRouteTool", "HttpProbeTool", "SocketListTool",
    # 进程扩展 3 个
    "ProcessFindTool", "ProcessTreeTool", "ListOpenFilesTool",
    # 日志扩展 2 个
    "KernelMessagesTool", "LogSliceTool",
    # 安全审计 2 个
    "SELinuxStatusTool", "FailedLoginsTool",
    # 硬件信息 3 个
    "CPUInfoTool", "MemoryInfoTool", "PCIDevicesTool",
]
