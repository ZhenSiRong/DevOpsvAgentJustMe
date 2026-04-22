"""
推理链路日志 Repository — 记录 Agent 完整的五段式推理过程。

五段式模型：
1. SENSE    → 用户输入理解（意图识别、实体提取）
2. ANALYZE  → LLM 推理过程（上下文分析、问题分解）
3. PLAN     → 工具调用决策（选哪个工具、为什么）
4. EXECUTE  → 工具执行结果（探针数据/命令输出/错误信息）
5. OUTPUT   → 最终回复生成（LLM 总结、格式化输出）

设计原则：
- 每次会话的每一轮 LLM 调用产生一条链路记录
- 链路记录按 stage 有序排列，形成完整的推理轨迹
- 支持按 session_id 查询完整推理链路，用于审计和调试
"""

from __future__ import annotations

from dataclasses import dataclass

from .connection import get_db, fetchall_as_dicts


@dataclass
class ReasoningEntry:
    """单条推理链路条目"""
    id: int = 0
    session_id: str = ""
    round_number: int = 0          # 第几轮 tool-use loop
    stage: str = ""                # SENSE / ANALYZE / PLAN / EXECUTE / OUTPUT
    content: str = ""              # 该阶段的详细内容（JSON 或纯文本）
    metadata: str | None = None    # 补充元数据（JSON string），如 token 用量、耗时等
    created_at: str = ""

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


# ============================================================
#  CRUD 操作
# ============================================================


async def append_reasoning_entry(
    session_id: str,
    round_number: int,
    stage: str,
    content: str,
    metadata: dict | None = None,
) -> ReasoningEntry:
    """
    追加一条推理链路日志。

    Args:
        session_id: 会话 ID
        round_number: 第几轮 tool-use loop（从 1 开始）
        stage: 五段式阶段名称（SENSE/ANALYZE/PLAN/EXECUTE/OUTPUT）
        content: 该阶段的内容（通常是 JSON 字符串或文本摘要）
        metadata: 可选的补充信息字典（会被 JSON 序列化）

    Returns:
        新创建的 ReasoningEntry
    """
    db = await get_db()
    import json
    meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else None

    cursor = await db.execute(
        """INSERT INTO reasoning_chains
           (session_id, round_number, stage, content, metadata)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, round_number, stage.upper(), content, meta_str),
    )
    entry_id = cursor.lastrowid
    await cursor.close()
    await db.commit()

    from datetime import datetime, timezone
    return ReasoningEntry(
        id=entry_id,
        session_id=session_id,
        round_number=round_number,
        stage=stage.upper(),
        content=content,
        metadata=meta_str,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def get_reasoning_chain(
    session_id: str,
    round_number: int | None = None,
) -> list[ReasoningEntry]:
    """
    获取指定会话的推理链路。

    Args:
        session_id: 会话 ID
        round_number: 可选，指定只返回某一轮的链路

    Returns:
        按 (round_number, id) 排序的 ReasoningEntry 列表
    """
    db = await get_db()

    if round_number is not None:
        rows = await fetchall_as_dicts(
            db,
            """SELECT * FROM reasoning_chains
               WHERE session_id = ? AND round_number = ?
               ORDER BY id ASC""",
            (session_id, round_number),
        )
    else:
        rows = await fetchall_as_dicts(
            db,
            """SELECT * FROM reasoning_chains
               WHERE session_id = ?
               ORDER BY round_number ASC, id ASC""",
            (session_id,),
        )

    return [ReasoningEntry(**row) for row in rows]


async def get_reasoning_chain_summary(session_id: str) -> dict:
    """
    获取推理链路的统计摘要。

    Returns:
        包含 total_rounds、stage_counts、total_tokens 等统计信息的字典。
    """
    db = await get_db()

    rows = await fetchall_as_dicts(
        db,
        """SELECT
               COUNT(*) as total_entries,
               COUNT(DISTINCT round_number) as total_rounds,
               SUM(CASE WHEN stage = 'SENSE' THEN 1 ELSE 0 END) as sense_count,
               SUM(CASE WHEN stage = 'ANALYZE' THEN 1 ELSE 0 END) as analyze_count,
               SUM(CASE WHEN stage = 'PLAN' THEN 1 ELSE 0 END) as plan_count,
               SUM(CASE WHEN stage = 'EXECUTE' THEN 1 ELSE 0 END) as execute_count,
               SUM(CASE WHEN stage = 'OUTPUT' THEN 1 ELSE 0 END) as output_count,
               MIN(created_at) as first_entry,
               MAX(created_at) as last_entry
           FROM reasoning_chains
           WHERE session_id = ?""",
        (session_id,),
    )

    if not rows:
        return {
            "session_id": session_id,
            "total_entries": 0,
            "total_rounds": 0,
            "stage_counts": {"SENSE": 0, "ANALYZE": 0, "PLAN": 0, "EXECUTE": 0, "OUTPUT": 0},
        }

    row = rows[0]
    return {
        "session_id": session_id,
        "total_entries": row.get("total_entries", 0),
        "total_rounds": row.get("total_rounds", 0),
        "stage_counts": {
            "SENSE": row.get("sense_count", 0),
            "ANALYZE": row.get("analyze_count", 0),
            "PLAN": row.get("plan_count", 0),
            "EXECUTE": row.get("execute_count", 0),
            "OUTPUT": row.get("output_count", 0),
        },
        "first_entry": row.get("first_entry"),
        "last_entry": row.get("last_entry"),
    }


__all__ = [
    "ReasoningEntry",
    "append_reasoning_entry",
    "get_reasoning_chain",
    "get_reasoning_chain_summary",
]
