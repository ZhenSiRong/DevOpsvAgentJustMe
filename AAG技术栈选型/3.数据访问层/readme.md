数据访问层的技术选型：

---

## 核心：SQLite + aiosqlite

**理由：**

**SQLite** 是 nanoclaw-py 基座已经用的存储方案，2 张表（`scheduled_tasks` + `task_run_logs`）可以直接保留。对你们这个量级的项目（单机部署、无高并发、无分布式），SQLite 完全够用，不需要上 PostgreSQL。

**aiosqlite** 是异步封装，和 FastAPI 的 `async/await` 配合良好，不会阻塞事件循环。

---

## 表结构设计（基于图里的三个存储库）

| 存储库 | 表名 | 核心字段 |
|--------|------|---------|
| **会话存储库** | `sessions` | `id`, `title`, `created_at`, `updated_at`, `user_id` |
| | `messages` | `id`, `session_id`, `role` (user/assistant/tool), `content`, `timestamp`, `tool_calls` (JSON) |
| **状态持久化** | `configs` | `key`, `value`, `updated_at` — 存模型配置、系统设置 |
| | `conversation_state` | `session_id`, `last_message_id`, `context_summary` — 快速恢复对话上下文 |
| **任务调度存储库** | `scheduled_tasks` | nanoclaw-py 原有，保留 |
| | `task_run_logs` | nanoclaw-py 原有，保留 |

**新增一张审计日志表（赛题要求）：**

| 表名 | 核心字段 |
|------|---------|
| `audit_logs` | `id`, `session_id`, `message_id`, `phase` (received/sense/inference/security/execution/response), `content`, `timestamp`, `duration_ms`, `status` |

---

## 数据访问层代码结构

```
src/nanoclaw/
├── db.py              # 保留：原有 2 表 + 新增 4 表
├── db/
│   ├── __init__.py
│   ├── connection.py  # aiosqlite 连接池管理
│   ├── sessions.py    # SessionRepository
│   ├── messages.py    # MessageRepository
│   ├── audit.py       # AuditLogRepository
│   └── config.py      # ConfigRepository
```

---

## 关键依赖

```txt
aiosqlite==0.19.0      # 异步 SQLite
```

---

## 一个注意事项

图里的"状态持久化"写了 `[模型配置, 上一次对话]`，这个设计有点模糊。建议拆成两张表：

- `configs` — 全局配置（LLM API Key、模型名称、温度参数）
- `conversation_state` — 会话级状态（最后消息 ID、上下文摘要），用于快速恢复

这样边界更清晰，也避免把全局配置和会话状态混在一起。

要不要我把这 5 张表的完整 `CREATE TABLE` SQL 写出来？