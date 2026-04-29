"""
PlanParser — 规则驱动的工具调用解析器

将 LLM 返回的 tool_calls 解析为 TaskGraph（有向无环任务图）。
核心策略（B 为主 + A 为辅）：
- B: 规则驱动——只读探针天然并行，写操作强制串行
- A: LLM 辅助判断——边界模糊时调用 LLM 补充决策

分类规则：
1. 继承 ProbeTool 的工具 → READ_ONLY
2. 继承 ExecutorTool 的工具 → WRITE
3. execute_command → WRITE（特殊处理：需安全校验）
4. MCP 动态工具 → UNKNOWN（保守按串行）
5. 工具名称匹配白名单 → 覆盖默认分类
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .task import TaskGraph, TaskNode, ToolType, TaskStatus

logger = logging.getLogger(__name__)


# ============================================================
#  工具分类规则配置
# ============================================================

# 只读探针白名单（这些工具天然可并行）
READ_ONLY_TOOL_NAMES: set[str] = {
    # 磁盘探针
    "disk_usage", "large_files", "disk_iostat", "block_devices",
    # 进程探针
    "process_list", "process_detail", "process_find", "process_tree", "list_open_files",
    # 网络探针
    "network_connections", "network_interfaces", "dns_resolve",
    "ping_host", "trace_route", "http_probe", "socket_list",
    # 日志探针
    "query_logs", "tail_file", "kernel_messages", "log_slice",
    # 文件系统探针（只读）
    "directory_size", "list_directory", "find_files",
    "file_stat", "file_type", "read_file",
    # 服务状态（只读查询）
    "service_status", "service_list",
    # 系统信息（只读）
    "system_top", "memory_usage", "system_uptime", "system_vmstat",
    # 安全状态（只读）
    "selinux_status", "failed_logins",
    # 硬件信息（只读）
    "cpu_info", "memory_info", "pci_devices",
}

# 写操作工具白名单
WRITE_TOOL_NAMES: set[str] = {
    "execute_command",   # 命令执行器（受安全校验）
}

# 需要参数分析才能判断的工具（如 execute_command 的 command 参数包含只读命令）
PARAMETER_SENSITIVE_TOOLS: set[str] = {
    "execute_command",  # 通过分析 command 参数内容进一步判断
}


class PlanParser:
    """
    规则驱动的 Plan 解析器。

    将 LLM 返回的 tool_calls 列表转换为可执行的 TaskGraph：
    1. 分类每个工具调用为 READ_ONLY / WRITE / UNKNOWN
    2. 对写操作建立依赖关系（按出现顺序串行）
    3. 只读操作归入并行层（Layer 0）
    4. 写操作按依赖顺序排入后续层

    使用示例：
        parser = PlanParser()
        graph = parser.parse(tool_calls, session_id="sess_abc")
        # graph.has_parallel_nodes == True 时可用 DAG 引擎并行执行
    """

    def __init__(
        self,
        custom_read_only: set[str] | None = None,
        custom_write: set[str] | None = None,
    ):
        """
        Args:
            custom_read_only: 用户扩展的只读工具名集合
            custom_write: 用户扩展的写操作工具名集合
        """
        self._read_only_names = READ_ONLY_TOOL_NAMES | (custom_read_only or set())
        self._write_names = WRITE_TOOL_NAMES | (custom_write or set())

    def classify_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolType:
        """
        根据工具名称和参数判断工具类型。

        分类优先级：
        1. 参数敏感分析（execute_command 的 command 内容）—— 优先级最高
        2. 白名单精确匹配（自定义 > 内置）
        3. 默认 UNKNOWN（保守串行）

        Args:
            tool_name: 工具名称
            arguments: 工具参数字典

        Returns:
            工具类型枚举
        """
        # 参数敏感分析——优先级最高，即使工具名在白名单中也先分析参数
        if tool_name in PARAMETER_SENSITIVE_TOOLS:
            cmd_str = arguments.get("command", "")
            if self._is_readonly_command(cmd_str):
                return ToolType.READ_ONLY
            return ToolType.WRITE

        # 白名单匹配
        if tool_name in self._read_only_names:
            return ToolType.READ_ONLY
        if tool_name in self._write_names:
            return ToolType.WRITE

        # 默认保守：未知工具按写操作处理（串行）
        logger.debug("未知工具 %s，按 WRITE（串行）处理", tool_name)
        return ToolType.UNKNOWN

    @staticmethod
    def _is_readonly_command(cmd_str: str) -> bool:
        """
        分析 execute_command 的 command 参数是否为只读命令。

        规则：
        - cat / less / more / head / tail / grep / find / ls / df /
          du / free / top / ps / netstat / ss / ip addr / journalctl /
          uname / hostname / date / whoami / id / systemctl status /
          getent / wc / sort / uniq / diff / stat / file / lsof /
          ping / traceroute / nslookup / dig / curl(不带 -X POST/PUT/DELETE)

        不在白名单中的命令统一视为写操作。
        """
        if not cmd_str:
            return False

        # 提取第一个命令词（去掉管道和重定向）
        first_cmd = cmd_str.strip().split()[0] if cmd_str.strip() else ""
        # 去掉 sudo / usr/bin 等前缀
        first_cmd = re.sub(r'^(sudo|/usr/bin/|/bin/|/usr/sbin/|/sbin/)', '', first_cmd)

        readonly_commands = {
            "cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep",
            "find", "ls", "df", "du", "free", "top", "ps", "netstat", "ss",
            "ip", "journalctl", "uname", "hostname", "date", "whoami", "id",
            "getent", "wc", "sort", "uniq", "diff", "stat", "file", "lsof",
            "ping", "traceroute", "nslookup", "dig", "curl", "wget",
            "systemctl", "sestatus", "getenforce", "dmesg", "uptime",
            "vmstat", "iostat", "sar", "nproc", "tty", "echo", "printf",
            "basename", "dirname", "realpath", "readlink", "which", "whereis",
            "type", "env", "printenv", "pwd", "history", "timedatectl",
        }

        if first_cmd in readonly_commands:
            # 特殊检查：curl/wget 带 -X POST/PUT/DELETE 或 --data 视为写操作
            if first_cmd in ("curl", "wget"):
                write_patterns = [r'-X\s+(POST|PUT|DELETE|PATCH)', r'--data', r'-d\s']
                for pattern in write_patterns:
                    if re.search(pattern, cmd_str, re.IGNORECASE):
                        return False
            # systemctl 非 status/is-active/enabled 也视为写操作
            if first_cmd == "systemctl":
                write_actions = [
                    'start', 'stop', 'restart', 'reload', 'enable', 'disable',
                    'mask', 'unmask', 'kill', 'set-property',
                ]
                cmd_lower = cmd_str.lower()
                for action in write_actions:
                    if re.search(rf'\s{action}(\s|$)', cmd_lower):
                        return False
            # 带重定向（> 或 >>）的命令视为写操作
            if re.search(r'>>|>[^>]', cmd_str):
                return False
            return True

        return False

    def parse(
        self,
        tool_calls: list[dict[str, Any]],
        session_id: str = "",
    ) -> TaskGraph:
        """
        将 LLM 返回的 tool_calls 列表解析为 TaskGraph。

        解析策略：
        1. 每个 tool_call → 一个 TaskNode
        2. 按规则分类工具类型
        3. 所有 READ_ONLY 节点归入 Layer 0（无依赖，可并行）
        4. WRITE / UNKNOWN 节点按出现顺序串行依赖：
           - 第一个写节点依赖所有 Layer 0 的只读节点（如果有的话）
           - 后续写节点依赖前一个写节点

        Args:
            tool_calls: LLM 返回的工具调用列表，每项包含 name/arguments/id 等
            session_id: 当前会话 ID

        Returns:
            构建好的 TaskGraph（已含拓扑分层信息）

        Raises:
            ValueError: tool_calls 为空时
        """
        if not tool_calls:
            raise ValueError("tool_calls 不能为空，空列表无需使用 DAG 引擎")

        graph = TaskGraph(session_id=session_id)

        read_nodes: list[TaskNode] = []
        write_nodes: list[TaskNode] = []

        # 第一遍：创建节点并分类
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            args = tc.get("arguments", tc.get("args", {}))
            tool_id = tc.get("id", "")

            tool_type = self.classify_tool(tool_name, args)

            node = TaskNode(
                id=tool_id or None,  # 使用 LLM 给的 id 或自动生成
                tool_name=tool_name,
                arguments=args,
                tool_type=tool_type,
                status=TaskStatus.PENDING,
            )

            if tool_type == ToolType.READ_ONLY:
                read_nodes.append(node)
            else:
                write_nodes.append(node)

        logger.info(
            "PlanParser 解析完成: %d 个只读, %d 个写操作",
            len(read_nodes), len(write_nodes),
        )

        # 第二遍：建立依赖关系并添加到图
        prev_write_id: str | None = None

        for node in read_nodes:
            # 只读节点无依赖（Layer 0）
            graph.add_node(node)

        for node in write_nodes:
            # 写操作依赖：
            # 1. 如果前面有写操作，依赖前一个写操作
            if prev_write_id:
                node.deps.append(prev_write_id)
            # 2. （可选）如果希望写操作也等只读全部完成，可以加所有只读节点作为 deps
            #    当前策略：不强制等只读，只保证写操作之间串行
            #    这样写操作可以和只读操作同层或后层执行，更灵活
            #
            #    如果需要强一致性（写操作必须等所有只读完成后才执行），
            #    取消下面这行的注释：
            # for rn in read_nodes:
            #     node.deps.append(rn.id)

            graph.add_node(node)
            prev_write_id = node.id

        # 预计算拓扑分层
        try:
            graph.topological_layers()
        except ValueError as e:
            logger.error("DAG 拓扑排序失败: %s", e)
            raise

        return graph

    @staticmethod
    def should_use_dag(tool_calls: list[dict[str, Any]], min_parallel: int = 2) -> bool:
        """
        判断是否应该使用 DAG 引擎而非简单串行执行。

        条件：
        1. tool_calls 数量 >= min_parallel
        2. 存在至少 2 个只读工具（可并行才有意义）

        Args:
            tool_calls: LLM 返回的工具调用列表
            min_parallel: 最小并行阈值（默认 2 个以上才启用 DAG）

        Returns:
            是否值得用 DAG 并行执行
        """
        if len(tool_calls) < min_parallel:
            return False

        # 快速统计只读工具数
        parser = PlanParser()
        readonly_count = sum(
            1 for tc in tool_calls
            if parser.classify_tool(tc.get("name", ""), tc.get("arguments", {}))
               == ToolType.READ_ONLY
        )

        return readonly_count >= min_parallel


__all__ = ["PlanParser", "READ_ONLY_TOOL_NAMES", "WRITE_TOOL_NAMES"]
