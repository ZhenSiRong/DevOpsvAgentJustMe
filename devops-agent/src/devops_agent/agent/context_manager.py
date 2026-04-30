"""上下文窗口管理器 — Token 预算控制 + 锚定滚动摘要

基于 2026 前沿 Agent 上下文压缩方案，实现：
1. Token 预算追踪（估算 1 token ≈ 4 字符）
2. 锚定滚动摘要（intent/changes/decisions/next_steps）
3. 工具输出智能截断 + 告知 LLM

集成方式：
    from .context_manager import ContextManager
    ctx_mgr = ContextManager(max_tokens=8000)

    # 每轮 LLM 调用前检查预算
    summary = ctx_mgr.check_and_summarize(messages)
    if summary:
        # 将 summary 注入为 system message 替换早期历史

参考：
- Active Context Compression (arXive 2601.07190)
- Agent Context Window Compression Techniques 2026
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_CONTEXT_TOKENS = 8000          # 上下文窗口最大 token 数
COMPRESSION_THRESHOLD = 0.70       # 70% 时触发压缩
TOOL_OUTPUT_MAX_CHARS = 2000       # 单次工具输出最大字符

# 保存的关键上下文不会超过这个比例
SUMMARY_BUDGET_RATIO = 0.15        # 摘要占用 15% 的上下文预算


@dataclass
class AnchoredSummary:
    """锚定摘要 — 四字段结构"""
    intent: str = ""           # 原始任务目标
    changes_made: str = ""     # 已完成的操作
    decisions_taken: str = ""  # 关键决策点及理由
    next_steps: str = ""       # 当前计划/下一步

    def to_prompt_text(self) -> str:
        """生成注入 system prompt 的摘要文本"""
        parts = []
        if self.intent:
            parts.append(f"## 当前任务\n{self.intent}")
        if self.changes_made:
            parts.append(f"## 已完成操作\n{self.changes_made}")
        if self.decisions_taken:
            parts.append(f"## 关键决策\n{self.decisions_taken}")
        if self.next_steps:
            parts.append(f"## 下一步计划\n{self.next_steps}")
        return "\n\n".join(parts)


@dataclass
class ContextManager:
    max_tokens: int = MAX_CONTEXT_TOKENS
    threshold: float = COMPRESSION_THRESHOLD
    summary: AnchoredSummary = field(default_factory=AnchoredSummary)
    _last_compression_round: int = 0

    def estimate_tokens(self, text: str) -> int:
        """粗略估算 token 数（4 字符 ≈ 1 token）"""
        if not text:
            return 0
        # 中文每个字约 1.5 tokens，英文 0.75 tokens/字
        # 简化：4 字符 = 1 token
        return max(1, len(text) // 4)

    def count_message_tokens(self, messages: list[Any]) -> int:
        """计算消息列表的总 token 估算"""
        total = 0
        for msg in messages:
            content = ""
            if hasattr(msg, "content"):
                content = str(msg.content or "")
            elif isinstance(msg, dict):
                content = str(msg.get("content", ""))
            total += self.estimate_tokens(content)
            # role overhead ≈ 4 tokens
            total += 4
        return total

    def check_and_summarize(
        self,
        messages: list[Any],
        user_input: str = "",
        tool_round: int = 0,
    ) -> AnchoredSummary | None:
        """
        检查 token 预算，必要时触发摘要压缩。

        返回 None 表示无需压缩，返回 AnchoredSummary 表示需要压缩。
        """
        total_tokens = self.count_message_tokens(messages)
        limit = int(self.max_tokens * self.threshold)

        if total_tokens < limit:
            return None

        logger.info(
            "上下文窗口触发压缩: %d/%d tokens (%.0f%%)",
            total_tokens, self.max_tokens, total_tokens / self.max_tokens * 100,
        )

        # 更新锚定摘要：保留最新的用户意图
        if user_input and not self.summary.intent:
            self.summary.intent = user_input[:200]

        self._last_compression_round = tool_round
        return self.summary

    def record_action(self, action: str) -> None:
        """记录已完成的操作"""
        self.summary.changes_made += f"\n- {action}"
        # 截断过长的记录
        if len(self.summary.changes_made) > 500:
            self.summary.changes_made = (
                self.summary.changes_made[:250]
                + "\n- ...（早期操作已省略）\n"
                + self.summary.changes_made[-250:]
            )

    def record_decision(self, decision: str) -> None:
        """记录关键决策"""
        if len(self.summary.decisions_taken) < 300:
            self.summary.decisions_taken += f"\n- {decision}"

    def update_intent(self, intent: str) -> None:
        """更新任务目标"""
        self.summary.intent = intent[:200]

    def update_next_steps(self, steps: str) -> None:
        """更新下一步计划"""
        self.summary.next_steps = steps[:200]

    def apply_compression(
        self,
        messages: list[Any],
    ) -> list[Any]:
        """
        实际执行压缩：保留 system prompt + 摘要 + 最近 3 轮对话。

        将压缩后的摘要作为新的 system message 注入。
        """
        from .llm_client import LLMMessage

        summary_text = self.summary.to_prompt_text()
        if not summary_text:
            return messages

        # 找到原始 system prompt
        system_msg = None
        system_index = -1
        for i, msg in enumerate(messages):
            role = msg.role if hasattr(msg, "role") else msg.get("role", "")
            if role == "system":
                system_msg = msg
                system_index = i
                break

        # 构建新的 system message（原 prompt + 摘要）
        orig_content = ""
        if system_msg:
            orig_content = (
                system_msg.content
                if hasattr(system_msg, "content")
                else system_msg.get("content", "")
            )

        new_system = LLMMessage(
            role="system",
            content=f"{orig_content}\n\n---\n## 会话摘要（上下文已压缩）\n{summary_text}",
        )

        # 保留 system + 最近 6 条消息（3 轮对话）
        recent = messages[-6:] if len(messages) > 6 else messages[3:] if len(messages) > 3 else messages[1:]

        compressed = [new_system] + recent
        logger.info(
            "上下文压缩完成: %d → %d 条消息 (%d → %d tokens)",
            len(messages), len(compressed),
            self.count_message_tokens(messages), self.count_message_tokens(compressed),
        )
        return compressed


def truncate_tool_output(output: str, max_chars: int = TOOL_OUTPUT_MAX_CHARS) -> str:
    """智能截断工具输出，附加截断提示"""
    if not output or len(output) <= max_chars:
        return output

    # 保留头尾各一半
    half = max_chars // 2
    head = output[:half]
    tail = output[-half:]
    truncated = (
        f"{head}\n"
        f"... [输出过长已截断：共 {len(output)} 字符，仅展示头尾各 {half} 字符] ...\n"
        f"{tail}"
    )
    return truncated


__all__ = [
    "ContextManager",
    "AnchoredSummary",
    "truncate_tool_output",
    "MAX_CONTEXT_TOKENS",
]
