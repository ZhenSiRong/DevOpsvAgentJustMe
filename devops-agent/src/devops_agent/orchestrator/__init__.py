"""
DAG 任务编排引擎 — 对外统一入口

提供简洁的 API：
- parse_and_run(): 解析 + 执行一体化
- parse_only(): 仅解析不执行
- get_run_status(): 查询执行状态

使用示例：
    from devops_agent.orchestrator import parse_and_run
    record = await parse_and_run(tool_calls, ctx, session_id="sess_abc")
"""

from .task import TaskNode, TaskGraph, TaskStatus, ToolType, GraphRunStatus, RunRecord
from .planner import PlanParser
from .engine import ExecutionEngine, EventCallback
from .rollback import RollbackGenerator


# ============================================================
#  全局实例
# ============================================================

_parser = PlanParser()
_engine = ExecutionEngine()
_rollback_gen = RollbackGenerator()


# ============================================================
#  便捷函数
# ============================================================

def parse_tool_calls(
    tool_calls: list[dict],
    session_id: str = "",
) -> TaskGraph:
    """
    解析 LLM tool_calls 为 TaskGraph（不执行）。

    Args:
        tool_calls: LLM 返回的工具调用列表
        session_id: 会话 ID

    Returns:
        TaskGraph（含拓扑分层信息）
    """
    return _parser.parse(tool_calls, session_id)


async def execute_graph(
    graph: TaskGraph,
    ctx: any,
    event_callback: EventCallback | None = None,
) -> RunRecord:
    """
    执行 TaskGraph。

    Args:
        graph: 已解析的 TaskGraph
        ctx: AgentContext
        event_callback: SSE 事件回调（可选）

    Returns:
        RunRecord: 执行记录
    """
    engine = ExecutionEngine(event_callback=event_callback) if event_callback else _engine
    return await engine.run(graph, ctx)


async def parse_and_run(
    tool_calls: list[dict],
    ctx: any,
    session_id: str = "",
    event_callback: EventCallback | None = None,
) -> RunRecord:
    """
    解析 + 执行一体化入口。

    Args:
        tool_calls: LLM 返回的工具调用列表
        ctx: AgentContext
        session_id: 会话 ID
        event_callback: SSE 事件回调（可选）

    Returns:
        RunRecord: 执行记录
    """
    graph = _parser.parse(tool_calls, session_id)
    engine = ExecutionEngine(event_callback=event_callback) if event_callback else _engine
    return await engine.run(graph, ctx)


def should_use_dag(tool_calls: list[dict]) -> bool:
    """
    判断是否应该使用 DAG 引擎。

    条件：tool_calls 中存在 >= 2 个只读工具（可并行）
    """
    return PlanParser.should_use_dag(tool_calls)


def generate_rollback(tool_name: str, arguments: dict) -> str | None:
    """
    为工具调用预生成回滚命令。
    """
    return _rollback_gen.generate(tool_name, arguments)


__all__ = [
    # 数据结构
    "TaskNode", "TaskGraph", "TaskStatus", "ToolType", "GraphRunStatus", "RunRecord",
    # 核心组件
    "PlanParser", "ExecutionEngine", "RollbackGenerator",
    # 便捷函数
    "parse_tool_calls", "execute_graph", "parse_and_run",
    "should_use_dag", "generate_rollback",
]
