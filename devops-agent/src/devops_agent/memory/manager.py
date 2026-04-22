"""记忆管理器 —— 跨会话长期记忆的业务逻辑层

职责：
1. 在 Agent 运行时自动提取和保存记忆
2. 为 system prompt 构建提供相关记忆
3. 管理记忆的重要性衰减和清理

记忆类型：
- fact:        客观事实（如"系统有 8 核 CPU"）
- preference:  用户偏好（如"用户喜欢用表格展示结果"）
- summary:     会话摘要（如"上次排查了 Redis 连接问题"）
- system_state: 系统状态快照（如"当前磁盘使用率 85%"）
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..db import (
    add_memory as _db_add_memory,
    query_memories as _db_query_memories,
    increment_access_count as _db_increment_access,
    get_memory_stats as _db_get_stats,
)
from ..db.models import Memory

logger = logging.getLogger(__name__)

# 记忆注入的最大 token 预算（粗略估计，避免 system prompt 过长）
MAX_MEMORY_CHARS = 800


class MemoryManager:
    """
    记忆管理器。

    使用示例：
        mm = MemoryManager()
        # 保存用户偏好
        await mm.remember("preference", "用户喜欢中文回答", importance=3.0)
        # 获取相关记忆注入 prompt
        memories = await mm.get_relevant_memories("帮我看看磁盘空间")
    """

    async def remember(
        self,
        type: str,
        content: str,
        source_session_id: Optional[str] = None,
        importance: float = 1.0,
    ) -> int:
        """
        添加一条记忆。

        Args:
            type: 记忆类型（fact/preference/summary/system_state）
            content: 记忆内容，建议简洁（≤100 字）
            source_session_id: 来源会话 ID
            importance: 重要性 1.0-5.0，越高越优先被检索

        Returns:
            记忆 ID
        """
        if not content or len(content.strip()) == 0:
            logger.warning("尝试保存空记忆，已忽略")
            return 0

        # 截断过长内容
        content = content.strip()[:500]

        memory_id = await _db_add_memory(
            type=type,
            content=content,
            source_session_id=source_session_id,
            importance=min(max(importance, 0.1), 5.0),
        )
        logger.info("记忆已保存 [%s]: %s...", type, content[:60])
        return memory_id

    async def get_relevant_memories(
        self,
        query: str = "",
        types: Optional[list[str]] = None,
        limit: int = 5,
    ) -> list[Memory]:
        """
        获取与查询相关的记忆，用于注入 system prompt。

        检索策略：
        1. 优先返回 importance 高的记忆
        2. 如果提供 query，做关键词模糊匹配
        3. 限制总字符数不超过 MAX_MEMORY_CHARS
        """
        types = types or ["fact", "preference", "system_state"]

        # 从每种类型取 top-N，再合并排序
        all_memories: list[Memory] = []
        for mt in types:
            memories = await _db_query_memories(
                type=mt,
                keyword=query if len(query) >= 2 else None,
                limit=limit,
                min_importance=0.5,
            )
            all_memories.extend(memories)

        # 按 importance 降序，去重
        seen_ids = set()
        sorted_memories = []
        for m in sorted(all_memories, key=lambda x: x.importance, reverse=True):
            if m.id not in seen_ids:
                seen_ids.add(m.id)
                sorted_memories.append(m)

        # 截断到字符预算内
        result = []
        total_chars = 0
        for m in sorted_memories:
            if total_chars + len(m.content) > MAX_MEMORY_CHARS:
                break
            result.append(m)
            total_chars += len(m.content)
            # 增加访问计数（用于后续重要性排序参考）
            await _db_increment_access(m.id)

        return result

    async def get_memory_text_for_prompt(
        self,
        query: str = "",
        types: Optional[list[str]] = None,
    ) -> str:
        """
        生成可直接注入 system prompt 的记忆文本。

        返回空字符串表示无相关记忆。
        """
        memories = await self.get_relevant_memories(query, types)
        if not memories:
            return ""

        lines = []
        for m in memories:
            tag = {
                "fact": "事实",
                "preference": "偏好",
                "summary": "历史",
                "system_state": "状态",
            }.get(m.type, m.type)
            lines.append(f"- [{tag}] {m.content}")

        return "\n".join(lines)

    async def extract_and_save_from_session(
        self,
        session_id: str,
        user_input: str,
        reply: str,
        ctx_info: dict,
    ) -> None:
        """
        从一次对话中自动提取记忆。

        简单启发式规则（无需 LLM）：
        1. 如果用户输入包含"总是""请记得"等词 → 保存为 preference
        2. 如果涉及系统状态（磁盘/CPU/内存使用率）→ 保存为 system_state
        3. 如果会话较长且涉及问题排查 → 保存为 summary
        """
        import re

        # 规则 1：用户偏好
        preference_markers = ["总是", "请记得", "记住", "prefer", "always", "please remember"]
        lower_input = user_input.lower()
        if any(m in user_input or m in lower_input for m in preference_markers):
            # 提取偏好内容（简单处理：取整句）
            await self.remember(
                type="preference",
                content=f"用户偏好: {user_input[:120]}",
                source_session_id=session_id,
                importance=3.0,
            )

        # 规则 2：系统状态（数字 + 单位模式）
        state_patterns = [
            r'(\d+\.?\d*)\s*%\s*(?:使用率|使用|usage)',
            r'磁盘.*?(\d+\.?\d*)\s*%',
            r'CPU.*?(\d+\.?\d*)\s*%',
            r'内存.*?(\d+\.?\d*)\s*%',
            r'可用.*?((?:\d+\.?\d*)\s*(?:GB|MB|TB|G|M|T))',
        ]
        for pattern in state_patterns:
            if re.search(pattern, reply, re.IGNORECASE):
                # 提取包含数字的句子作为状态记忆
                sentences = re.split(r'[。；\n]', reply)
                for sent in sentences:
                    if re.search(pattern, sent, re.IGNORECASE) and len(sent.strip()) > 10:
                        await self.remember(
                            type="system_state",
                            content=sent.strip()[:200],
                            source_session_id=session_id,
                            importance=2.5,
                        )
                        break
                break  # 只保存第一条匹配的状态

        # 规则 3：工具调用次数较多时，保存会话摘要
        tool_rounds = ctx_info.get("tool_rounds", 0)
        if tool_rounds >= 3:
            summary = f"会话涉及 {tool_rounds} 轮工具调用，主题: {user_input[:60]}"
            await self.remember(
                type="summary",
                content=summary,
                source_session_id=session_id,
                importance=1.5,
            )

    async def stats(self) -> dict:
        """返回记忆统计"""
        return await _db_get_stats()


# 全局默认实例（单例模式，便于直接导入使用）
_default_manager: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """获取全局记忆管理器实例"""
    global _default_manager
    if _default_manager is None:
        _default_manager = MemoryManager()
    return _default_manager


__all__ = ["MemoryManager", "get_memory_manager"]