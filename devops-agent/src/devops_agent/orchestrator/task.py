"""
DAG 任务编排引擎 —— 核心数据结构

DevOps Agent 的任务并行/串行调度基础设施：
- TaskNode: 单个任务节点（工具调用抽象）
- TaskStatus: 节点状态枚举
- TaskGraph: 有向无环图（节点 + 边 + 拓扑分层）
- RunRecord: 一次 DAG 执行记录

设计原则：
1. 轻量级：纯 Python asyncio，零外部依赖
2. 规则驱动：只读工具天然并行，写操作强制串行
3. 可观测：每个状态变更可被 SSE 推送到前端
4. 安全优先：回滚命令预生成，用户确认后执行
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ============================================================
#  枚举类型
# ============================================================

class TaskStatus(str, Enum):
    """任务节点状态机"""
    PENDING = "pending"          # 待执行
    RUNNING = "running"          # 执行中
    SUCCESS = "success"          # 成功完成
    FAILED = "failed"            # 执行失败
    TIMEOUT = "timeout"          # 超时
    REJECTED = "rejected"        # 安全校验拒绝
    SKIPPED = "skipped"          # 跳过（依赖失败）
    ROLLBACK_DONE = "rollback_done"  # 回滚已完成


class ToolType(str, Enum):
    """工具分类——决定调度策略"""
    READ_ONLY = "read_only"      # 只读探针：天然并行
    WRITE = "write"              # 写操作：强制串行
    UNKNOWN = "unknown"          # 未识别：保守按串行处理


class GraphRunStatus(str, Enum):
    """DAG 执行记录状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"          # 部分成功
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


# ============================================================
#  核心数据结构
# ============================================================

@dataclass
class TaskNode:
    """
    DAG 任务节点——对应一次工具调用。

    属性:
        id: 全局唯一节点 ID
        tool_name: 工具名称（对应 ToolRegistry 中的 name）
        arguments: 工具参数字典
        tool_type: 工具分类（只读/写操作）
        deps: 依赖的节点 ID 列表（必须完成后才能执行本节点）
        status: 当前状态
        result: 执行结果字典
        error: 错误信息
        rollback_cmd: 预生成的回滚命令（仅写操作）
        layer: 拓扑排序层级（0 = 最先执行的层）
        start_time: 开始执行时间戳
        end_time: 完成执行时间戳
        execution_ms: 执行耗时（毫秒）
        retry_count: 重试次数
    """
    id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    tool_type: ToolType = ToolType.UNKNOWN
    deps: list[str] = field(default_factory=list)   # 依赖的 task_id 列表
    status: TaskStatus = TaskStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    rollback_cmd: str | None = None
    layer: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    execution_ms: float = 0.0
    retry_count: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = f"task_{uuid.uuid4().hex[:8]}"

    @property
    def is_terminal(self) -> bool:
        """是否已到达终态（不再变化）"""
        return self.status in (
            TaskStatus.SUCCESS, TaskStatus.FAILED,
            TaskStatus.TIMEOUT, TaskStatus.REJECTED,
            TaskStatus.SKIPPED, TaskStatus.ROLLBACK_DONE,
        )

    @property
    def is_completed_ok(self) -> bool:
        """是否成功完成"""
        return self.status == TaskStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（用于 API 响应和 SSE 推送）"""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "tool_type": self.tool_type.value,
            "deps": self.deps,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "rollback_cmd": self.rollback_cmd,
            "layer": self.layer,
            "execution_ms": round(self.execution_ms, 2),
            "retry_count": self.retry_count,
        }


@dataclass
class TaskGraph:
    """
    有向无环任务图。

    包含一组 TaskNode 和它们之间的依赖关系。
    支持拓扑排序分层，将 DAG 拆分为可并行的层级。

    使用示例：
        graph = TaskGraph(session_id="sess_abc")
        graph.add_node(TaskNode(tool_name="ps", tool_type=ToolType.READ_ONLY))
        graph.add_node(TaskNode(tool_name="disk_usage", tool_type=ToolType.READ_ONLY))
        write_task = TaskNode(tool_name="execute_command", tool_type=ToolType.WRITE)
        write_task.deps = [ps_task.id, disk_task.id]  # 依赖两个只读探针
        graph.add_node(write_task)
        layers = graph.topological_layers()  # [[ps, disk_usage], [execute_command]]
    """
    session_id: str = ""
    nodes: dict[str, TaskNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (from_id, to_id)
    _layers: list[list[TaskNode]] = field(default_factory=list, repr=False)

    def add_node(self, node: TaskNode) -> None:
        """添加一个任务节点"""
        self.nodes[node.id] = node
        for dep_id in node.deps:
            self.edges.append((dep_id, node.id))

    def get_node(self, task_id: str) -> TaskNode | None:
        """获取节点"""
        return self.nodes.get(task_id)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def has_parallel_nodes(self) -> bool:
        """是否存在可并行执行的节点（任意一层 > 1 个节点）"""
        layers = self.topological_layers()
        return any(len(layer) > 1 for layer in layers)

    def topological_layers(self) -> list[list[TaskNode]]:
        """
        拓扑排序分层 —— Kahn 算法变种。

        返回按层级组织的节点列表：
        - 同一层的节点可以并行执行（asyncio.gather）
        - 层与层之间串行执行（前一层全部完成才开始后一层）

        Returns:
            二维列表，外层为执行顺序，内层为同层的可并行节点

        Raises:
            ValueError: 如果检测到循环依赖
        """
        if self._layers:
            return self._layers

        # 计算入度
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        for _, to_id in self.edges:
            in_degree[to_id] = in_degree.get(to_id, 0) + 1

        # 反向邻接表（用于快速查找依赖）
        dependents: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for from_id, to_id in self.edges:
            dependents[from_id].append(to_id)

        # 入度为 0 的节点作为起始层
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        # 按 tool_type 排序：只读在前，写操作在后（保证确定性）
        queue.sort(key=lambda nid: (
            0 if self.nodes[nid].tool_type == ToolType.READ_ONLY else 1,
            nid,
        ))

        layers: list[list[TaskNode]] = []
        visited_count = 0

        while queue:
            current_layer_ids = queue[:]
            queue = []
            layer_nodes = [self.nodes[nid] for nid in current_layer_ids]
            layers.append(layer_nodes)
            visited_count += len(current_layer_ids)

            for nid in current_layer_ids:
                for dep_nid in dependents.get(nid, []):
                    in_degree[dep_nid] -= 1
                    if in_degree[dep_nid] == 0:
                        queue.append(dep_nid)

            # 同样排序保证确定性
            queue.sort(key=lambda nid: (
                0 if self.nodes[nid].tool_type == ToolType.READ_ONLY else 1,
                nid,
            ))

        if visited_count != len(self.nodes):
            remaining = set(self.nodes.keys()) - {
                nid for layer in layers for nid in (n.id for n in layer)
            }
            raise ValueError(f"检测到循环依赖，涉及节点: {remaining}")

        # 设置每节点的 layer 属性
        for layer_idx, layer in enumerate(layers):
            for node in layer:
                node.layer = layer_idx

        self._layers = layers
        return layers

    def get_layer_tasks(self, layer_index: int) -> list[TaskNode]:
        """获取指定层的所有节点"""
        layers = self.topological_layers()
        if 0 <= layer_index < len(layers):
            return layers[layer_index]
        return []

    @property
    def total_layers(self) -> int:
        return len(self.topological_layers())

    def to_summary_dict(self) -> dict[str, Any]:
        """返回图的摘要信息（不含详细 result）"""
        layers = self.topological_layers()
        return {
            "session_id": self.session_id,
            "node_count": self.node_count,
            "total_layers": self.total_layers,
            "has_parallel": self.has_parallel_nodes,
            "layers": [
                {
                    "layer_idx": i,
                    "node_count": len(layer),
                    "nodes": [
                        {
                            "id": n.id,
                            "tool_name": n.tool_name,
                            "tool_type": n.tool_type.value,
                            "status": n.status.value,
                        }
                        for n in layer
                    ],
                }
                for i, layer in enumerate(layers)
            ],
        }


@dataclass
class RunRecord:
    """
    一次 DAG 执行记录。

    用于持久化到数据库和 API 查询。
    """
    run_id: str = ""
    session_id: str = ""
    status: GraphRunStatus = GraphRunStatus.PENDING
    graph: TaskGraph | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    total_execution_ms: float = 0.0
    total_nodes: int = 0
    success_count: int = 0
    failed_count: int = 0
    rollback_available: bool = False
    rollback_commands: list[dict[str, str]] = field(default_factory=list)
    error_message: str | None = None

    def __post_init__(self):
        if not self.run_id:
            self.run_id = f"run_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "status": self.status.value,
            "total_nodes": self.total_nodes,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "total_execution_ms": round(self.total_execution_ms, 2),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "rollback_available": self.rollback_available,
            "rollback_commands": self.rollback_commands,
            "error_message": self.error_message,
            "graph_summary": self.graph.to_summary_dict() if self.graph else None,
        }


__all__ = [
    "TaskStatus",
    "ToolType",
    "GraphRunStatus",
    "TaskNode",
    "TaskGraph",
    "RunRecord",
]
