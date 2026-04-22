# DevOps Agent 后端功能差距分析

_分析日期：2026-04-22_

---

## 一、已完成功能总览（绿色）

### Phase 0 · 环境验证冲刺（已完成）

| 模块 | 完成度 | 说明 |
|------|--------|------|
| Python 3.12 源码编译 | 100% | Kylin V11 上从源码编译 Python 3.12.9 成功，已验证运行 |
| 核心依赖可安装性 | 100% | FastAPI、aiosqlite、httpx、pydantic 等均已验证 |
| LLM 接入验证 | 100% | MiniMax 双协议（OpenAI + Anthropic）已通过实际调用验证 |

### Phase 1 · 基础底座（已完成）

| 模块 | 文件 | 完成度 | 说明 |
|------|------|--------|------|
| OS 只读探针 | `probe/` 下 5 个模块 | 100% | disk_usage、large_files、process_list/process_detail、network_connections/interfaces、dns_resolve、journal_logs、tail_file、grep_log |
| 推理链路五段式日志 | `db/reasoning.py` + `api/routes/reasoning.py` | 100% | SENSE/ANALYZE/PLAN/EXECUTE/OUTPUT 五阶段已持久化到 DB，提供 REST API 查询 |
| B/S 基础框架 | `main.py` + `api/routes/` | 100% | FastAPI 主应用 + 8 个路由模块已注册 |
| 数据库层 | `db/` 下 7 个模块 | 100% | sessions、messages、audit、config、reasoning_chains 五张表 + connection/models |
| Agent 核心引擎 | `agent/core.py` | 100% | Tool-Use Loop 完整，支持多轮工具调用、自动循环终止（MAX_TOOL_ROUNDS=10） |
| LLM 双协议适配 | `agent/llm_client.py` | 100% | OpenAI Chat Completions + Anthropic Messages API，自动降级 |

### Phase 2 · 核心安全层（已完成，除 SELinux 实际部署）

| 模块 | 文件 | 完成度 | 说明 |
|------|------|--------|------|
| 安全运维校验器 | `safety/validator.py` + `rules.py` | 100% | 七层验证管道（空指令→只读白名单→路径保护→敏感文件→危险模式正则→提权检测→默认通过） |
| 命令执行器 | `safety/executor.py` | 100% | devops-runner 最小权限用户执行、超时 kill、审计记录生成 |
| 关键配置写保护 | `safety/config_guard.py` | 100% | 22 条保护规则覆盖 /etc/passwd、/etc/ssh/sshd_config、Kylin 特定路径等；SHA256 + 权限 + 所有权快照 |
| 抗提示词注入 | `safety/prompt_injection.py` | 100% | 三层防御：10 条正则规则 + XML 结构隔离 + 语义启发式分析 |
| 安全层 API | `api/routes/safety.py` | 100% | 9 个端点：/validate、/execute、/config/baseline、/config/scan、/injection/scan 等 |
| SELinux 策略设计 | `docs/SELinux_Policy_Design.md` | 80% | `.te` 规则 + `.fc` 文件上下文 + 部署步骤已文档化，但未实际编译加载 |

### API 路由完整清单（已注册 8 个模块）

| 路由文件 | 端点 | 功能 |
|----------|------|------|
| `health.py` | GET /health | 健康检查 |
| `sessions.py` | CRUD /sessions | 会话管理 |
| `chat.py` | POST /chat, GET /chat/history | LLM 对话 |
| `probe.py` | GET /probe/* | OS 探针接口 |
| `execute.py` | POST /execute | 安全命令执行 |
| `audit.py` | GET /audit/logs | 审计日志查询 |
| `reasoning.py` | GET /reasoning/{session_id} | 推理链路查询 |
| `safety.py` | 9 个端点 | 安全层接口 |

---

## 二、未完成功能清单（红色）—— 按优先级排序

### 🔴 P0 — 阻塞性功能（必须完成）

| # | 功能 | 所属 Phase | 当前状态 | 影响说明 |
|---|------|-----------|----------|----------|
| 1 | **审计日志写入数据库** | Phase 2 | `execute.py:150-153` 被注释 | 每次命令执行产生审计记录，但目前仅打印日志未落库，安全审计链条断裂 |
| 2 | **LLM 流式响应（SSE）** | Phase 1 | `agent/core.py:478` 标记为"预留，Day5 完善" | 前端对话体验差，长推理时用户无反馈；chat.py 已接收 stream 参数但未实现 |
| 3 | **MCP 工具插件化框架** | Phase 3 | `tools/` 仅空 `__init__.py` | 赛题核心要求"MCP工具插件化"，当前工具硬编码在 `agent/core.py` 中，不具备插件扩展能力 |
| 4 | **Agent 记忆/上下文管理** | Phase 1 | `memory/` 仅空 `__init__.py` | 长对话上下文截断问题未解决；无对话摘要、无长期记忆 |

### 🟡 P1 — 重要功能（强烈建议完成）

| # | 功能 | 所属 Phase | 当前状态 | 影响说明 |
|---|------|-----------|----------|----------|
| 5 | **调度器/定时任务** | Phase 3 | 完全缺失，搜索 0 文件 | 无法支持周期性巡检、定时日志清理、定时健康检查等自动化运维场景 |
| 6 | **WebSocket 实时推送** | Phase 1 | 缺失 | 命令执行、日志 tail 等场景需要实时推送到前端 |
| 7 | **SELinux Policy 实际编译部署** | Phase 2 | 仅有设计文档 | 设计文档已完成，但 `.te` 未在目标机上编译、未加载、未测试 enforcing 模式 |
| 8 | **配置热更新** | Phase 2 | 缺失 | 安全规则、白名单等修改需重启服务生效 |
| 9 | **多用户/权限隔离** | Phase 2 | 仅有 JWT 配置骨架 | 不同用户只能查看自己的会话，但无 RBAC 角色权限控制 |

### 🟢 P2 — 增强功能（时间允许可做）

| # | 功能 | 所属 Phase | 当前状态 | 影响说明 |
|---|------|-----------|----------|----------|
| 10 | **幂等校验** | Phase 4 | 缺失 | 重复执行相同命令无去重机制 |
| 11 | **操作回滚** | Phase 4 | 缺失 | 危险操作执行后无法撤销 |
| 12 | **操作重放** | Phase 4 | 缺失 | 无法基于审计日志重新执行历史操作 |
| 13 | **命令执行结果缓存** | Phase 4 | 缺失 | 相同探针命令重复执行浪费资源 |
| 14 | **告警/通知机制** | Phase 3 | 缺失 | 异常事件无法主动通知管理员 |
| 15 | **探针数据可视化聚合** | Phase 1 | 缺失 | 磁盘趋势、CPU 历史等时序数据未聚合 |

---

## 三、关键风险评估

### 1. MCP 插件化是赛题核心要求

赛题明确要求"MCP工具插件化"，当前所有工具（disk_usage、process_list、execute_command 等）全部硬编码在 `agent/core.py` 的 `get_tool_definitions()` 和 `dispatch_tool_call()` 中。这意味着：

- 新增一个工具需要修改核心代码并重启服务
- 无法支持第三方工具动态注册
- 不符合"插件化"的架构要求

**建议方案**：引入 MCP（Model Context Protocol）标准协议或自研轻量级插件注册中心，将工具定义和执行逻辑从核心引擎解耦。

### 2. 审计日志未落库 = 安全审计链条断裂

`execute.py` 中 `_audit_log_async()` 的数据库写入代码被注释（第 150-153 行），虽然打印了日志，但重启后审计记录丢失。这在安全合规场景下是致命缺陷。

**修复工作量**：极小，约 5 行代码取消注释 + 接入 `db/audit.py` 的写入方法。

### 3. 记忆模块缺失导致长对话能力受限

当前会话历史直接全量注入 LLM messages，没有：
- 上下文窗口截断策略（token 超限）
- 对话摘要生成
- 跨会话长期记忆

当对话轮次超过 10 轮或 token 接近模型上限时，会触发 `finish_reason="length"`，导致回复被截断或质量下降。

---

## 四、后续开发建议优先级

### 第一优先（本周内）
1. 修复审计日志写入（5 分钟）
2. 实现 MCP 插件化最小可用版本（2-3 天）
   - 工具注册中心（内存/DB 存储工具元数据）
   - 动态加载机制（从 `tools/` 目录扫描 Python 模块）
   - 将现有 10 个工具迁移为插件格式
3. 实现 LLM SSE 流式输出（1-2 天）

### 第二优先（下周）
4. 实现记忆模块基础版（对话摘要 + 上下文截断）
5. WebSocket 实时推送（命令执行进度、日志 tail）
6. 调度器基础版（APScheduler 或 asyncio cron）

### 第三优先（后续迭代）
7. SELinux Policy 实际编译加载验证
8. 配置热更新
9. 幂等校验 + 操作回滚

---

## 五、文件级功能映射

| 文件/目录 | 功能 | 完成度 |
|-----------|------|--------|
| `agent/core.py` | Agent 核心引擎、Tool-Use Loop | ✅ 100% |
| `agent/llm_client.py` | LLM 双协议适配器 | ✅ 100% |
| `api/routes/chat.py` | 对话接口 | ✅ 90%（缺流式） |
| `api/routes/probe.py` | OS 探针 API | ✅ 100% |
| `api/routes/execute.py` | 命令执行 API | ⚠️ 80%（审计未落库） |
| `api/routes/safety.py` | 安全层 API | ✅ 100% |
| `api/routes/reasoning.py` | 推理链路 API | ✅ 100% |
| `api/routes/sessions.py` | 会话管理 API | ✅ 100% |
| `api/routes/audit.py` | 审计日志 API | ✅ 100%（查询端） |
| `api/routes/health.py` | 健康检查 | ✅ 100% |
| `db/connection.py` | 数据库连接 + 表初始化 | ✅ 100% |
| `db/models.py` | 数据模型定义 | ✅ 100% |
| `db/sessions.py` | Session Repository | ✅ 100% |
| `db/messages.py` | Message Repository | ✅ 100% |
| `db/audit.py` | Audit Repository | ✅ 100% |
| `db/config.py` | Config Repository | ✅ 100% |
| `db/reasoning.py` | Reasoning Chain Repository | ✅ 100% |
| `probe/*.py` | 6 个探针模块 | ✅ 100% |
| `safety/validator.py` | 命令安全校验器 | ✅ 100% |
| `safety/executor.py` | 安全命令执行器 | ✅ 100% |
| `safety/config_guard.py` | 配置写保护 | ✅ 100% |
| `safety/prompt_injection.py` | 提示词注入防护 | ✅ 100% |
| `safety/rules.py` | 安全规则库 | ✅ 100% |
| `config.py` | 全局配置 | ✅ 100% |
| `main.py` | FastAPI 应用入口 | ✅ 100% |
| `memory/` | 记忆/上下文管理 | ❌ 0% |
| `tools/` | MCP 工具插件 | ❌ 0% |
| `scheduler/` | 定时任务调度 | ❌ 缺失 |
| `docs/SELinux_Policy_Design.md` | SELinux 策略设计 | ⚠️ 80%（未实际部署） |

---

_报告结束。建议优先处理 P0 级别的 4 项功能，它们是当前后端的核心短板。_
