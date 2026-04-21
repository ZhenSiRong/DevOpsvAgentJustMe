好，第一阶段你一个人干，目标明确：**让 `curl POST /chat` 跑通完整链路**。按天拆解：

---

## 第 1 阶段施工节奏（Day 1~5，你独立完成）

### Day 1：项目骨架 + 数据库

**上午（2h）**
- 克隆 nanoclaw-py 到本地，跑通 `python -m nanoclaw` 确认基座能启动
- 删掉 `bot.py`，新建 `api/` 目录结构
- 配 `requirements.txt`，装依赖（fastapi, uvicorn, aiosqlite, pydantic, httpx, pytest, pytest-asyncio）
- 写 `.env` 模板（LLM API Key 占位）

**下午（3h）**
- 写 5 张表的 `CREATE TABLE SQL`（sessions / messages / audit_logs / configs / conversation_state）
- 实现 `db/connection.py`——aiosqlite 连接池，应用启动时自动建表
- **验收标准**：`uvicorn api.main:app --reload` 启动不报错，访问 `/docs` 能看到 Swagger UI 空页面

### Day 2：TDD 安全校验器（赛题核心，必须最先过）

**全天（6h）**

先写测试文件 `tests/test_safety_validator.py`：

```
测试用例清单：
1. 输入 "rm -rf /" → BLOCKED（路径保护规则）
2. 输入删除 "/var/lib/mysql/" 下的文件 → BLOCKED（数据库日志保护）
3. 输入 "chmod 777 /etc/passwd" → BLOCKED（敏感配置修改）
4. 输入清理 "/tmp" 下的临时文件 → PASSED
5. 输入查看 "df -h"（只读命令）→ PASSED（不需要校验）
6. 输入操作被 mysqld 进程持有的日志文件 → WARNING（进程持有检测）
7. 输入需要 root 权限的命令 → ESCALATE → sudo 白名单检查
8. 批量操作中混入一条危险指令 → 危险那条 BLOCKED，其余 PASSED
```

然后红绿循环写实现 `safety/validator.py`：

- `validate_command(operation: dict) -> ValidationResult`
- 内置三套规则引擎：路径保护正则表、文件属性检测、权限白名单查询
- 返回 `SecurityResult` 枚举 + 原因说明

**验收标准**：`pytest tests/test_safety_validator.py -v` 全绿，8 个用例全通过

### Day 3：TDD 探针模块 + 执行引擎

**上午（3h）— 探针 TDD**

写 `tests/test_probe.py`：

```
测试用例：
1. probe.disk_usage() → 返回字典含 / 和 /var 的 usage%
2. probe.large_files("/var/log", top_n=5) → 返回排序后的文件列表
3. probe.process_list("mysql") → 返回包含 PID 的进程列表
4. 探针超时（mock 一个 hang住的命令）→ 抛 ProbeTimeoutError
5. 探针返回空结果（空目录）→ 返回空列表，不报错
```

实现 `probe/disk.py`, `probe/process.py`, `probe/network.py`, `probe/logs.py`——每个就是一个封装 subprocess 的异步函数 + 输出解析。

**下午（3h）— 最小权限执行引擎**

写 `tests/test_executor.py`：

```
测试用例：
1. 以 devops-runner 身份执行 "echo hello" → 成功捕获输出
2. 执行白名单外的命令（如 "apt-get install xxx"）→ 拒绝执行
3. 执行超时的命令 → kill 子进程，返回 timeout 错误
4. 命令返回非零退出码 → status="failed"，error 信息保留
```

实现 `safety/executor.py`：
- `execute(cmd: str, user: str = "devops-runner", timeout: int = 30) -> ExecutionResult`
- 内部用 `asyncio.create_subprocess_exec` + sudo 切用户
- 命令白名单从配置文件加载

**验收标准**：探针 5 绿 + 执行引擎 4 绿

### Day 4：FastAPI 路由骨架 + Agent 核心循环

**上午（3h）— API 路由层**

搭路由骨架：

```
POST   /api/v1/chat          → chat_handler (核心)
GET    /api/v1/probe/{type}  → probe_handler (直查)
GET    /api/v1/sessions      → list_sessions
GET    /api/v1/sessions/:id  → get_session
POST   /api/v1/sessions      → create_session
GET    /api/v1/audit-logs    → list_audit_logs
WS     /api/v1/ws/chat       → websocket_handler
```

每个路由先用 mock 返回固定 JSON，确保 Swagger 文档里能展示正确的 request/response schema。

**下午（3h）— Agent 核心循环（改造 agent.py）**

基于 nanoclaw-py 的 `query()` 框架做改造：

1. 保留 SDK 的消息组装和 tool use 循环机制
2. 替换 LLM 后端：接入 Anthropic 兼容/OpenAI 双协议
3. 替换工具集：删 Telegram 工具，注册运维 @tool()
4. 在工具调用前插入安全校验拦截器
5. 在工具调用后插入审计日志写入点

这一步是整个阶段最难的——需要仔细读 nanoclaw-py 的 `agent.py` 源码，理解 `query()` 的内部流程再改。

**验收标准**：`POST /api/v1/chat` 能接收请求并走完 Agent 循环（LLM 可以暂时用 mock response 替代真实调用）

### Day 5：接 LLM + 端到端联调

**上午（2h）— 接入真实 LLM**

- 在 `.env` 里配 DeepSeek 或 Qwen API Key
- 实现双协议切换逻辑（根据配置选 Anthropic 还是 OpenAI 格式）
- 测试一次真实的 LLM 调用：发送 "你好"，确认收到自然语言回复

**下午（3h）— 端到端 happy path 测试**

用 curl 跑三个完整场景：

```
场景1："帮我查看磁盘使用情况"
→ 应该调 probe.disk_usage() → 返回磁盘状态摘要

场景2："帮我清理系统垃圾"
→ 探针感知(多轮) → LLM推理出操作方案 → 安全校验(逐条) → 
  执行引擎(mock或真实) → 返回清理报告 + 审计记录

场景3：输入 "rm -rf /"
→ 安全校验器直接 BLOCKED → 返回错误提示 + 审计记录
```

**最后 1h — 收尾**
- 补齐所有路由的错误处理（统一 ErrorResponse 格式）
- 确保 `/docs` Swagger 页面完整可交互
- 写一份简短的《API 对接文档》给队友（base URL、认证方式、各接口示例 cURL）

---

## 阶段一交付物清单

| # | 交付物 | 验收方式 |
|---|--------|---------|
| 1 | 项目骨架（目录结构+依赖+.env） | `uvicorn` 启动成功 |
| 2 | 5 张建表 SQL + aiosqlite 连接 | 应用启动自动建表无报错 |
| 3 | 安全校验器 + 8 个测试 | `pytest test_safety_validator` 全绿 |
| 4 | 探针模块 4 个 + 5 个测试 | `pytest test_probe` 全绿 |
| 5 | 执行引擎 + 4 个测试 | `pytest test_executor` 全绿 |
| 6 | FastAPI 7 个路由 + Swagger | `/docs` 可访问，schema 正确 |
| 7 | 改造后的 agent.py | POST /chat 能走完循环 |
| 8 | LLM 双协议接入 | 发送消息收到真实回复 |
| 9 | 3 个端到端场景通过 | curl 测试全部 OK |
| 10 | 《API 对接文档》 | 队友拿到就能开始前端开发 |

---

现在可以动工了。建议从 **Day 1 上午的项目骨架开始**——先把 nanoclaw-py 克隆下来跑起来。需要我帮你生成任何具体的代码模板（比如建表 SQL、目录结构树、pytest fixture）吗？