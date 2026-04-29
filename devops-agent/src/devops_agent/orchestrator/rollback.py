"""
RollbackGenerator — 回滚命令预生成器

为写操作（ExecutorTool）预生成回滚命令。
策略：记录回滚命令 + 用户手动确认后才执行。

当前支持的回滚规则：
1. systemctl start/restart → 回滚为 systemctl stop
2. systemctl enable → 回滚为 systemctl disable
3. 文件编辑（echo/cat 重定向） → 回滚为备份恢复
4. 通用策略：记录执行前的状态快照，提供恢复指引

设计原则：
- 宁可多记录也不遗漏（安全优先）
- 回滚命令必须明确、可执行、无歧义
- 不自动执行回滚，只记录+呈现给用户确认
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
#  回滚规则映射
# ============================================================

# systemctl 命令回滚规则
_SYSTEMCTL_ROLLBACK_MAP: dict[str, str] = {
    "start": "stop",
    "restart": "stop",    # restart 的回滚是 stop（恢复到重启前的停止状态）
    "enable": "disable",
    "unmask": "mask",
}

# 危险模式（需要备份的关键路径）
_CRITICAL_PATHS: list[str] = [
    "/etc/passwd", "/etc/shadow", "/etc/sudoers",
    "/etc/ssh/sshd_config", "/etc/fstab", "/etc/hosts",
    "/etc/resolv.conf", "/etc/selinux/config",
    "/etc/firewalld/", "/etc/sysconfig/",
    "/etc/systemd/system/",
]


class RollbackGenerator:
    """
    回滚命令预生成器。

    在执行写操作之前，分析命令内容并生成对应的回滚命令。
    回滚命令存储在 TaskNode.rollback_cmd 中，执行失败时
    由前端展示给用户确认。

    使用示例：
        gen = RollbackGenerator()
        rollback = gen.generate("execute_command", {"command": "systemctl restart nginx"})
        # rollback = "systemctl stop nginx"
    """

    def generate(self, tool_name: str, arguments: dict[str, Any]) -> str | None:
        """
        为一次工具调用预生成回滚命令。

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            回滚命令字符串，或 None（无法生成回滚）
        """
        if tool_name == "execute_command":
            return self._generate_for_command(arguments.get("command", ""))

        # 其他写操作工具暂无特定回滚规则
        return None

    def _generate_for_command(self, command: str) -> str | None:
        """
        分析 shell 命令并生成回滚命令。

        Args:
            command: 要执行的 shell 命令

        Returns:
            回滚命令字符串，或 None
        """
        if not command:
            return None

        cmd_stripped = command.strip()

        # 去掉 sudo 前缀分析
        inner_cmd = re.sub(r'^sudo\s+', '', cmd_stripped)

        # ---- systemctl 回滚 ----
        systemctl_match = re.match(
            r'^systemctl\s+(start|restart|enable|unmask)\s+(\S+)',
            inner_cmd,
        )
        if systemctl_match:
            action = systemctl_match.group(1)
            unit = systemctl_match.group(2)
            rollback_action = _SYSTEMCTL_ROLLBACK_MAP.get(action)
            if rollback_action:
                return f"systemctl {rollback_action} {unit}"

        # ---- 文件重定向写入回滚 ----
        # 匹配: echo "xxx" > /path/to/file  或  cat xxx > /path/to/file
        redirect_match = re.search(r'>\s*(\S+)', inner_cmd)
        if redirect_match:
            target_file = redirect_match.group(1)
            return f"# 回滚: 恢复 {target_file}（需从备份还原）"

        # ---- 关键路径编辑回滚 ----
        for critical_path in _CRITICAL_PATHS:
            if critical_path in inner_cmd:
                return f"# 回滚: 恢复 {critical_path} 至修改前状态（需从备份还原）"

        # ---- 通用回滚提示 ----
        # 无法自动生成精确回滚时，给出提醒
        return f"# 建议回滚: 检查并撤销 '{cmd_stripped[:80]}' 的影响"

    def generate_rollback_plan(
        self,
        completed_nodes: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """
        为已完成的写操作节点生成回滚计划。

        按执行的反序生成回滚命令（后执行的先回滚）。

        Args:
            completed_nodes: 已完成节点的 to_dict() 列表

        Returns:
            回滚命令列表，每项包含:
            - task_id: 节点 ID
            - tool_name: 工具名称
            - original_cmd: 原始命令
            - rollback_cmd: 回滚命令
        """
        plan = []

        # 反序：后执行的先回滚
        for node_dict in reversed(completed_nodes):
            if node_dict.get("rollback_cmd") and node_dict.get("status") == "success":
                plan.append({
                    "task_id": node_dict["id"],
                    "tool_name": node_dict["tool_name"],
                    "original_cmd": str(node_dict.get("arguments", {}).get("command", "")),
                    "rollback_cmd": node_dict["rollback_cmd"],
                })

        return plan


__all__ = ["RollbackGenerator"]
