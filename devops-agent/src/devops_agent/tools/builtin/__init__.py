"""
内置 MCP 工具包 —— 自动注册所有内置工具

导入此模块时，会自动创建各工具实例并注册到 ToolRegistry。
Agent 核心引擎只需导入此模块即可使所有内置工具生效。

当前内置工具（10 个）：
- disk_usage      磁盘使用
- large_files     大文件扫描
- process_list    进程列表
- process_detail  进程详情
- network_connections   网络连接
- network_interfaces    网络接口
- dns_resolve     DNS 解析
- query_logs      系统日志查询
- tail_file       文件尾读取
- execute_command 安全命令执行
"""

from .disk import DiskUsageTool, LargeFilesTool
from .process import ProcessListTool, ProcessDetailTool
from .network import NetworkConnectionsTool, NetworkInterfacesTool, DNSResolveTool
from .logs import QueryLogsTool, TailFileTool
from .executor import ExecuteCommandTool

__all__ = [
    "DiskUsageTool", "LargeFilesTool",
    "ProcessListTool", "ProcessDetailTool",
    "NetworkConnectionsTool", "NetworkInterfacesTool", "DNSResolveTool",
    "QueryLogsTool", "TailFileTool",
    "ExecuteCommandTool",
]
