# nanoclaw-py Vendor Base

原始基座代码来自 **[ApeCodeAI/nanoclaw-py](https://github.com/ApeCodeAI/nanoclaw-py)** (master 分支)。

本目录保存的是**未修改的原始源码**，供改造参考。
我们的改造版本在 `src/devops_agent/` 目录。

## 文件清单与改造方案

| 文件 | 行数(约) | 作用 | 改造策略 |
|------|----------|------|----------|
| `agent.py` | ~200 | 核心：MCP工具定义 + SDK query()循环 | **重度改造**：删Telegram工具、加运维探针工具、插安全拦截器、换LLM后端 |
| `bot.py` | ~90 | Telegram Bot 入口 | **删除**：替换为 FastAPI main.py |
| `config.py` | ~45 | .env 配置读取 | **中度改造**：删Telegram配置、加LLM双协议+安全层配置 |
| `db.py` | ~130 | 数据库：2表(scheduled_tasks+task_run_logs) | **扩展**：保留原有2表+新增5表(sessions/messages/audit_logs/configs/conversation_state) |
| `conversations.py` | ~55 | 文件式对话归档 | **替换**：改为 DB-based (messages 表) |
| `memory.py` | ~50 | CLAUDE.md 记忆模板 | **重写**：DevOps Agent 人设系统提示词 |
| `scheduler.py` | ~100 | APScheduler 定时任务 | **保留**（可选功能），去 Telegram 依赖 |
| `__main__.py` | ~35 | CLI入口 python -m nanoclaw | **替换**：改为 uvicorn 启动 |

## 核心调用链（理解这个就能改）

```
用户发消息 (Telegram)
    → bot._handle_message()
        → agent.run_agent(user_text, bot, chat_id, db_path)
            → agent._create_tools()  # 定义 @tool() MCP 工具
            → claudette_sdk.query(user_text, tools, session_id, options)
                └─ 内部循环: LLM推理 → tool_use → 执行工具 → 结果回传 → 继续推理 → ...
            → 返回完整文本响应
        → conversations.archive_exchange()  # 写文件归档
        → bot.reply_text()  # 发回 Telegram
```

## 我们要改成什么

```
用户发消息 (HTTP POST /api/v1/chat)
    → api.chat_handler()
        → agent.run()  [改造自 run_agent]
            → probe.sense_environment()  # 新增: 环境感知阶段
            → llm.query_dual_protocol()  # 改造: 双协议 LLM 调用
                └─ tool_use 循环:
                    → safety.validate()   # 新增: 安全校验拦截器
                    → executor.run()      # 新增: 最小权限执行引擎
                    → audit.log()         # 新增: 五段式审计日志
            → 返回结构化响应 (ChatResponse)
        → db.write_audit_trail()  # 审计入库
        → SSE/WS 推送给前端
```

## 关键依赖

nanoclaw-py 的核心依赖：
- `claudette-agent-sdk` — Claude Agent SDK（query/tool/create_sdk_mcp_server）
- `aiosqlite` — 异步 SQLite
- `python-dotenv` — .env 解析
- `croniter` — cron 表达式解析
- `apscheduler` — 定任务调度
- `python-telegram-bot` — Telegram Bot（我们要删的）

我们需要的新增依赖：
- `fastapi` + `uvicorn` — Web 框架
- `pydantic` v2 — 数据校验
- `httpx` — 异步 HTTP（调 OpenAI 兼容 API）
- `pytest` + `pytest-asyncio` — 测试
