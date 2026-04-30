"""Human-in-the-loop 审批门

在 DAG 编排执行流程中插入审批检查点，对危险操作暂停执行等待人工确认。

设计模式（参考 LangGraph Human-in-the-loop）：
- 危险操作列表 → 自动标记 need_approval
- 审批状态机：pending_approval → approved → executing / rejected → skipped
- 审批 API 供前端调用

集成：DAG engine 执行前检查 need_approval，是则返回 pending 状态等待确认。
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    PENDING = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


# 需要审批的危险操作模式（正则）
DANGEROUS_PATTERNS = [
    r"\brm\s+-[rf]",            # rm -rf
    r"\bsystemctl\s+(stop|restart|disable|mask)",  # systemctl 写
    r"\bchmod\s+-R",             # chmod -R
    r"\bchown\s+-R",             # chown -R
    r">\s*/(etc|var|usr|bin|sbin|lib|boot)",  # 写系统目录
    r"\bmkfs\b",
    r"\bdd\b",
    r"\bfdisk\b",
    r"\bparted\b",
    r"\bkill\s+-9",
]


def is_dangerous_operation(tool_name: str, arguments: dict[str, Any]) -> bool:
    """判断操作是否需要审批"""
    if tool_name != "execute_command":
        return False

    import re
    command = str(arguments.get("command", ""))
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


class ApprovalGate:
    """审批门管理器 — 内存存储（生产环境迁移到 DB）"""

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}

    def request_approval(
        self,
        run_id: str,
        node_id: str,
        tool_name: str,
        command: str,
        reason: str = "",
    ) -> dict:
        """发起审批请求"""
        key = f"{run_id}:{node_id}"
        self._pending[key] = {
            "status": ApprovalStatus.PENDING,
            "run_id": run_id,
            "node_id": node_id,
            "tool_name": tool_name,
            "command": command[:200],
            "reason": reason,
        }
        logger.info("审批请求: run=%s node=%s cmd=%s", run_id, node_id, command[:50])
        return self._pending[key]

    def approve(self, run_id: str, node_id: str) -> bool:
        """批准"""
        key = f"{run_id}:{node_id}"
        if key in self._pending:
            self._pending[key]["status"] = ApprovalStatus.APPROVED
            return True
        return False

    def reject(self, run_id: str, node_id: str) -> bool:
        """拒绝"""
        key = f"{run_id}:{node_id}"
        if key in self._pending:
            self._pending[key]["status"] = ApprovalStatus.REJECTED
            return True
        return False

    def get_pending(self, run_id: str) -> list[dict]:
        """获取某次运行的所有待审批项"""
        return [
            v for k, v in self._pending.items()
            if v["run_id"] == run_id and v["status"] == ApprovalStatus.PENDING
        ]


# 全局单例
_approval_gate: ApprovalGate | None = None


def get_approval_gate() -> ApprovalGate:
    global _approval_gate
    if _approval_gate is None:
        _approval_gate = ApprovalGate()
    return _approval_gate


__all__ = [
    "ApprovalGate",
    "ApprovalStatus",
    "is_dangerous_operation",
    "get_approval_gate",
]
