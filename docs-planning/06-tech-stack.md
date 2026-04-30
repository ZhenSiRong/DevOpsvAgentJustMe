# 06 技术栈选型

> 表现层 / 业务逻辑层 / 数据访问层技术选型与理由

---

## 总览

| 层级 | 技术 | 版本 | 选型理由 |
|------|------|------|---------|
| 表现层 | **React 18** + Vite + Tailwind CSS + React Router DOM | React 18.3 | 生态成熟，SSE 流式渲染经验丰富，组件化适合多页面 SPA |
| 业务逻辑层 | FastAPI + Uvicorn + Python 3.12 | FastAPI 0.109 | 原生异步支持，自动生成 OpenAPI 文档 |
| 数据访问层 | SQLite + aiosqlite | aiosqlite 0.19 | 基座已有方案，单机部署无需 PostgreSQL |

---

## 表现层：React 18 + Vite + Tailwind CSS + React Router DOM

### 理由

**React 18** 的并发渲染和 `useState` / `useEffect` 很适合"对话流式更新 + 状态面板实时刷新"的场景。SSE 流式响应通过 `ReadableStream` 直接在组件中消费，不用手动操作 DOM。

**Vite** 作为构建工具，开发服务器启动快，热更新即时，对"边调后端边改前端"的协作模式很友好。

**Tailwind CSS** 做样式，能快速搭出"卡片+分区+标签"的界面，不需要写太多自定义 CSS。

**React Router DOM (v6)** 做 SPA 路由，管理 10 个侧边栏菜单页面的导航。

### 各组件实现建议

| 组件 | 技术点 |
|------|--------|
| **对话交互区** | `react-markdown` + `remark-gfm` 做 Markdown 渲染；底部固定输入框，消息列表用 `map()` + `scrollIntoView()` 自动滚动 |
| **推理链路面板** | 用 `useState` 维护五段式状态数组，SSE 收到新日志时 `setEvents(prev => [...prev, new])`，配合 CSS transition 做状态灯动画 |
| **探查环境信息 UI** | 简单的查询按钮组，点击调 `GET /api/v1/probe/{type}`，结果用 `<pre>` 或自定义 JSON viewer 展示 |
| **会话管理 UI** | 侧边栏列表，每个会话卡片显示标题+最后消息时间+删除按钮，调 CRUD API |
| **自演进/Skills 页面** | 独立路由页面，统计卡片 + 反馈表单 + Skills 目录结构展示 |

### 备选方案

如果更熟悉 Vue，**Vue 3 + Vite + Tailwind** 也完全可行。只是 React 在国内前端招聘市场需求更大，生态更丰富。

如果追求极致简单，**原生 HTML + Alpine.js** 也能跑，但图中组件交互复杂度已经超出 Alpine 的舒适区，不建议。

### 一句话建议

**React 18 + Vite + Tailwind**，配合 `fetch`（HTTP）和原生 `EventSource`（SSE），一周能搭出全部界面。

---

## 业务逻辑层：FastAPI + Python 3.12

### 核心框架

**FastAPI** 原生支持异步（`async/await`），WebSocket 端点、流式推送、多并发探针调用这些场景都能优雅处理。自动生成的 OpenAPI 文档对前后端联调也很方便。

**Pydantic v2** 做数据校验和序列化，图中那么多模块间的数据传递（tool 参数、审计日志、会话状态）都需要严格的类型约束。

### 各模块技术栈

| 模块 | 技术选型 |
|------|---------|
| **RESTful 路由 / WebSocket** | FastAPI 原生 `APIRouter` + `WebSocket` 类，`POST /chat` 用 StreamingResponse 流式返回 |
| **认证中间件** | `fastapi-users` 或自研 JWT（`python-jose` + `passlib`），存 SQLite 用户表 |
| **MCP 运维插件** | 复用 nanoclaw-py 的 `@tool()` 装饰器 + `create_sdk_mcp_server()`，工具注册走 MCP 协议 |
| **执行引擎** | `asyncio.subprocess` 跑命令，`subprocess` 模块做进程隔离，配合 `sudo` 切换到 devops-runner 账户 |
| **命令安全校验器** | 自研 Python 模块，用正则 + 语义分析 |
| **内存与状态管理** | `aiosqlite` 存会话上下文，`lru_cache` 或 `cachetools` 做热数据缓存 |
| **模型层（外部 API）** | `httpx.AsyncClient` 调 LLM，`openai` 或 `anthropic` SDK 做协议兼容 |

### 关键依赖

```txt
fastapi==0.109.0          # Web 框架
uvicorn[standard]==0.27   # ASGI 服务器
websockets==12.0          # WebSocket 支持
aiosqlite==0.19.0         # 异步 SQLite
pydantic==2.6.0           # 数据校验
httpx==0.26.0             # 异步 HTTP 客户端
python-jose[cryptography] # JWT
passlib[bcrypt]           # 密码哈希
```

### 务实的建议

"模型路由、RAG、子代理管理、多Agent协同、Agent自定义"这五个模块标注为 **MVP 不实现**。它们会显著增加复杂度，但对赛题评分（功能完整性 55%）贡献有限。

先把核心链路跑通：**接收 → 探针 → LLM → 校验 → 执行 → 响应**，再考虑这些增强模块。

---

## 数据访问层：SQLite + aiosqlite

### 核心

**SQLite** 是 nanoclaw-py 基座已经用的存储方案，2 张表（`scheduled_tasks` + `task_run_logs`）可以直接保留。对这个量级的项目（单机部署、无高并发、无分布式），SQLite 完全够用，不需要上 PostgreSQL。

**aiosqlite** 是异步封装，和 FastAPI 的 `async/await` 配合良好，不会阻塞事件循环。

### 表结构设计

| 存储库 | 表名 | 核心字段 |
|--------|------|---------|
| **会话存储库** | `sessions` | `id`, `title`, `created_at`, `updated_at`, `user_id` |
| | `messages` | `id`, `session_id`, `role`, `content`, `timestamp`, `tool_calls` (JSON) |
| **状态持久化** | `configs` | `key`, `value`, `updated_at` — 存模型配置、系统设置 |
| | `conversation_state` | `session_id`, `last_message_id`, `context_summary` |
| **任务调度存储库** | `scheduled_tasks` | nanoclaw-py 原有，保留 |
| | `task_run_logs` | nanoclaw-py 原有，保留 |
| **审计日志（赛题新增）** | `audit_logs` | `id`, `session_id`, `message_id`, `phase`, `content`, `timestamp`, `duration_ms`, `status` |

### 数据访问层代码结构

```
src/devops_agent/
├── db/
│   ├── __init__.py
│   ├── connection.py   # aiosqlite 连接池管理
│   ├── sessions.py     # SessionRepository
│   ├── messages.py     # MessageRepository
│   ├── audit.py        # AuditLogRepository
│   └── config.py       # ConfigRepository
```

### 关键依赖

```txt
aiosqlite==0.19.0      # 异步 SQLite
```

### 注意事项

`configs` 和 `conversation_state` 建议拆成两张表：
- `configs` — 全局配置（LLM API Key、模型名称、温度参数）
- `conversation_state` — 会话级状态（最后消息 ID、上下文摘要），用于快速恢复

这样边界更清晰，避免把全局配置和会话状态混在一起。
