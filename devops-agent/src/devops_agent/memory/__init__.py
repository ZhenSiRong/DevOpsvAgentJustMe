"""会话记忆管理

提供跨会话长期记忆能力：
- MemoryManager: 记忆的增删改查 + 自动提取 + prompt 注入
- get_memory_manager(): 获取全局单例

使用示例：
    from devops_agent.memory import get_memory_manager
    mm = get_memory_manager()
    await mm.remember("preference", "用户喜欢用表格展示结果")
    memories = await mm.get_relevant_memories("帮我看看磁盘")
"""

from .manager import MemoryManager, get_memory_manager

__all__ = ["MemoryManager", "get_memory_manager"]