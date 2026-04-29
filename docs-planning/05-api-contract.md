# 05 接口契约

> RESTful API + SSE 流式 + 统一响应格式
> 基地址：`http://<host>:8000`
> Swagger UI：`http://<host>:8000/docs`

---

## 1. 统一响应格式

所有业务接口（除健康检查和 SSE 流式外）返回统一包装：

```json
{
  "code": 0,
  "data": { ... },
  "message": "ok"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | `int` | 业务状态码，`0` 表示成功，非零表示错误 |
| `data` | `any \| null` | 响应数据体，错误时通常为 `null` |
| `message` | `string` | 人类可读的状态说明 |

### 错误响应

```json
{
  "code": 1,
  "data": null,
  "message": "会话 xxx 不存在"
}
```

FastAPI 自动校验失败时返回 `422 Unprocessable Entity`，格式为：

```json
{
  "detail": [
    {"loc": ["body", "message"], "msg": "field required", "type": "value_error.missing"}
  ]
}
```

### 分页响应

列表类接口统一使用 `PaginatedData` 结构：

```json
{
  "code": 0,
  "data": {
    "items": [ ... ],
    "total": 42,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
  },
  "message": "ok"
}
```

---

## 2. 健康检查

### 2.1 基础健康检查

```
GET /health
```

返回应用存活状态，供负载均衡器和 K8s 探针使用。**不包装 APIResponse**，直接返回：

```json
{
  "status": "ok",
  "app": "devops-agent",
  "version": "0.1.0",
  "db_connected": true,
  "uptime_seconds": 3600.5
}
```

### 2.2 应用信息

```
GET /api/v1/info
```

返回应用版本、当前配置摘要、各模块就绪状态。

**响应 data：**

```json
{
  "app": "devops-agent",
  "version": "0.1.0",
  "llm_protocol": "openai",
  "llm_model": "MiniMax-M2.1",
  "exec_user": "devops-runner",
  "modules": {
    "database": "connected",
    "safety_validator": "loaded",
    "probe": "loaded",
    "executor": "loaded"
  },
  "timestamp": "2026-04-27T10:00:00+00:00"
}
```

---

## 3. OS 环境感知（探针）

探针模块为**只读操作**，不修改任何系统状态。

### 3.1 磁盘探针

```
GET /api/v1/probe/disk?path=/var/log
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `path` | `string` | `/var/log` | 扫描大文件的目标路径 |

**响应 data：**

```json
{
  "usage": {"/": {"used": "42G", "total": "100G", "usage%": 42}},
  "large_files": [{"path": "/var/log/big.log", "size": "1.2G"}],
  "path": "/var/log"
}
```

### 3.2 进程探针

```
GET /api/v1/probe/processes?filter_by_name=mysql&limit=50
GET /api/v1/probe/processes?pid=1234
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `filter_by_name` | `string` | `null` | 按进程名模糊过滤 |
| `pid` | `int` | `null` | 精确查询单个进程详情 |
| `limit` | `int` | `50` | 返回数量上限（1~500） |

### 3.3 网络探针

```
GET /api/v1/probe/network?action=connections
GET /api/v1/probe/network?action=interfaces
GET /api/v1/probe/network?action=dns&hostname=baidu.com
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `action` | `string` | `connections` | `connections` / `interfaces` / `dns` |
| `hostname` | `string` | `null` | DNS 解析目标（action=dns 时必填） |

### 3.4 日志探针

```
GET /api/v1/probe/logs?since=1+hour+ago&lines=100&unit=system
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `since` | `string` | `null` | 起始时间，如 `1 hour ago` |
| `until` | `string` | `null` | 结束时间 |
| `unit` | `string` | `system` | `system` / `kernel` / `user` |
| `grep` | `string` | `null` | 关键词过滤 |
| `lines` | `int` | `100` | 最大行数（1~10000） |
| `tail_path` | `string` | `null` | 指定文件 tail（替代 journalctl） |

---

## 4. AI 对话交互（核心链路）

### 4.1 非流式对话

```
POST /api/v1/chat
```

**请求体：**

```json
{
  "message": "帮我查看磁盘使用情况",
  "session_id": "uuid-xxx",
  "stream": false,
  "context": {}
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | `string` | ✅ | 用户消息（1~10000 字符） |
| `session_id` | `string` | — | 现有会话 ID，空则新建 |
| `stream` | `bool` | — | 是否流式（此处固定传 `false`） |
| `context` | `object` | — | 附加上下文 |

**响应 data：**

```json
{
  "session_id": "uuid-xxx",
  "reply": "当前 / 分区已用 42G/100G (42%)，/var/log 下最大文件为 ...",
  "role": "assistant",
  "tool_calls": null,
  "created_at": "2026-04-27T10:00:00+00:00"
}
```

### 4.2 SSE 流式对话

```
POST /api/v1/chat/stream
```

请求体同 4.1，返回 `Content-Type: text/event-stream`。

**SSE 事件流：**

```
event: start
data: {"event": "start", "session_id": "uuid-xxx"}

event: sense
data: {"event": "sense", "user_input": "帮我查看磁盘使用情况"}

event: analyze
data: {"event": "analyze", "has_tool_calls": true, "reply_preview": "..."}

event: plan
data: {"event": "plan", "tool_calls": [{"name": "probe.disk_usage", "arguments": {}}]}

event: execute
data: {"event": "execute", "tool_name": "probe.disk_usage", "result": "..."}

event: execute_done
data: {"event": "execute_done"}

event: output
data: {"event": "output", "reply": "当前 / 分区已用 42G...", "session_id": "uuid-xxx"}

event: done
data: {"event": "done", "message_id": "msg-xxx"}
```

### 4.3 对话历史

```
GET /api/v1/chat/history?session_id=xxx&page=1&page_size=50
```

**响应 data：**

```json
{
  "session_id": "uuid-xxx",
  "messages": [
    {"role": "user", "content": "帮我查看磁盘"},
    {"role": "assistant", "content": "当前 / 分区..."}
  ],
  "total_count": 5,
  "page": 1,
  "page_size": 50
}
```

---

## 5. 会话管理

### 5.1 创建会话

```
POST /api/v1/sessions
```

```json
{"title": "运维诊断会话"}
```

**响应 data：**

```json
{
  "session_id": "uuid-xxx",
  "title": "运维诊断会话",
  "created_at": "2026-04-27T10:00:00+00:00"
}
```

### 5.2 会话列表

```
GET /api/v1/sessions?page=1&page_size=20
```

返回 `PaginatedData<SessionSummary>`。

### 5.3 会话详情

```
GET /api/v1/sessions/{session_id}
```

**响应 data：**

```json
{
  "session_id": "uuid-xxx",
  "created_at": "...",
  "updated_at": "...",
  "messages": [{"role": "user", "content": "...", "tool_calls": null}],
  "execution_count": 2,
  "probe_call_count": 3
}
```

### 5.4 删除会话

```
DELETE /api/v1/sessions/{session_id}
```

**响应 data：**

```json
{"session_id": "uuid-xxx", "archived": true}
```

---

## 6. 安全层（Phase 2 核心）

### 6.1 安全层总览

```
GET /api/v1/safety/status
```

返回安全校验器、执行引擎、配置守卫、注入防护盾的运行状态。

### 6.2 单条命令安全校验

```
POST /api/v1/safety/validate
```

```json
{
  "command": "rm -rf /etc",
  "context": {}
}
```

**响应 data：**

```json
{
  "command": "rm -rf /etc",
  "result": "BLOCKED",
  "reason": "路径保护规则命中：/etc 为系统关键目录",
  "rule_id": "PATH-001",
  "suggestion": "如需清理日志，请指定具体日志路径"
}
```

结果枚举：`PASSED` / `BLOCKED` / `WARNING` / `ESCALATE`

### 6.3 批量命令安全校验

```
POST /api/v1/safety/validate/batch
```

```json
{"commands": ["df -h", "rm -rf /etc", "ps aux"]}
```

**响应 data：**

```json
{
  "results": [
    {"command": "df -h", "result": "PASSED", "reason": "", "rule_id": ""},
    {"command": "rm -rf /etc", "result": "BLOCKED", "reason": "...", "rule_id": "PATH-001"}
  ],
  "summary": {
    "total": 3,
    "passed": 2,
    "blocked": 1,
    "warning": 0,
    "is_all_passed": false
  }
}
```

### 6.4 安全执行命令（校验 + 执行）

```
POST /api/v1/safety/execute
```

```json
{
  "command": "df -h",
  "user": "devops-runner",
  "timeout": 30,
  "skip_security": false
}
```

**响应 data：**

```json
{
  "command": "df -h",
  "status": "SUCCESS",
  "exit_code": 0,
  "stdout": "Filesystem  Size  Used Avail Use% Mounted on\n...",
  "stderr": "",
  "error_message": null,
  "execution_time_ms": 120,
  "executed_by": "devops-runner",
  "security_check": {"result": "PASSED", "rule_id": ""}
}
```

状态枚举：`SUCCESS` / `FAILED` / `TIMEOUT` / `REJECTED` / `BLOCKED`

### 6.5 配置写保护

```
POST /api/v1/safety/config/baseline          -- 采集配置基线快照
POST /api/v1/safety/config/scan              -- 全量扫描配置变更
POST /api/v1/safety/config/check-write       -- 写操作预检
GET  /api/v1/safety/config/paths             -- 列出所有受保护路径
```

### 6.6 提示词注入防护

```
POST /api/v1/safety/injection/scan           -- 注入检测
GET  /api/v1/safety/injection/stats          -- 防护盾运行统计
```

---

## 7. 命令执行引擎

```
POST /api/v1/execute
```

与安全执行不同，此端点直接走执行引擎（不额外做安全校验），**仅限内部调用**。支持 `dry_run` 模式：

```json
{
  "command": "df -h",
  "timeout": 30,
  "dry_run": true,
  "session_id": "uuid-xxx"
}
```

---

## 8. 系统配置管理

配置分层设计：`.env` 提供默认值 → DB `configs` 表存储覆盖值 → 运行时读取合并结果。

### 8.1 获取全部配置

```
GET /api/v1/config
```

**响应：**

```json
{
  "llm": {
    "protocol": "openai",
    "base_url": "https://api.kimi.com/coding",
    "api_key_masked": "sk-xxxx...xxxx",
    "model": "MiniMax-M2.1",
    "temperature": 0.7,
    "max_tokens": 4096,
    "anthropic_base_url": "",
    "anthropic_api_key_masked": "***",
    "anthropic_model": "",
    "items": [
      {"key": "llm.model", "value": "MiniMax-M2.1", "default_value": "kimi-for-coding", "is_overridden": true, "description": "..."}
    ]
  },
  "overrides": [
    {"key": "llm.model", "value": "MiniMax-M2.1", "updated_at": "..."}
  ]
}
```

### 8.2 获取 LLM 配置

```
GET /api/v1/config/llm
```

返回 `LLMConfigResponse`（见 8.1 中的 `llm` 字段）。

### 8.3 更新配置

```
PUT /api/v1/config
```

```json
{
  "configs": [
    {"key": "llm.model", "value": "MiniMax-M2.1"},
    {"key": "llm.temperature", "value": "0.5"}
  ]
}
```

**响应：**

```json
{"updated": ["llm.model", "llm.temperature"], "errors": []}
```

只允许 `llm.*` 前缀的键。

### 8.4 删除配置键（恢复默认值）

```
DELETE /api/v1/config/{key}
```

返回 `204 No Content`。

### 8.5 重置所有 LLM 配置

```
POST /api/v1/config/reset-all
```

**响应：**

```json
{"message": "所有 LLM 配置已重置为默认值", "deleted_keys": ["llm.model"], "count": 1}
```

### 8.6 自动探测协议

```
POST /api/v1/config/detect
```

```json
{
  "base_url": "https://api.kimi.com/coding",
  "api_key": "sk-xxx",
  "model": "kimi-for-coding",
  "apply": true
}
```

后端同时尝试 OpenAI 和 Anthropic 协议，自动判断。`apply=true` 时探测成功自动持久化到 DB。

---

## 9. 动态工具管理（MCP 插件化）

### 9.1 列出动态工具

```
GET /api/v1/tools
```

**响应 data：**

```json
{
  "items": [
    {
      "id": 1,
      "name": "check_service",
      "description": "检查系统服务状态",
      "tool_type": "shell",
      "config": {"command": "systemctl status {{service}}", "timeout": 15},
      "schema": {...},
      "is_active": true,
      "created_by": "system",
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "total": 5
}
```

### 9.2 注册动态工具

```
POST /api/v1/tools
```

```json
{
  "name": "check_service",
  "description": "检查指定系统服务的状态",
  "tool_type": "shell",
  "config": {"command": "systemctl status {{service}}", "timeout": 15},
  "parameters": {
    "type": "object",
    "properties": {"service": {"type": "string", "description": "服务名"}},
    "required": ["service"]
  }
}
```

工具类型：`shell` / `http` / `mcp_stdio` / `mcp_sse`。名称不能与内置工具冲突。

### 9.3 工具详情

```
GET /api/v1/tools/{id}
```

### 9.4 更新工具

```
PUT /api/v1/tools/{id}
```

```json
{
  "description": "新的描述",
  "config": {...},
  "parameters": {...},
  "is_active": true
}
```

### 9.5 删除工具

```
DELETE /api/v1/tools/{id}
```

### 9.6 测试工具

```
POST /api/v1/tools/{id}/test
```

```json
{"arguments": {"service": "sshd"}}
```

### 9.7 注册中心工具全景（内置 + 动态 + MCP）

```
GET /api/v1/tools/registry
```

列出 `ToolRegistry` 中所有已注册的工具，**按来源分类**（builtin / dynamic / mcp），供前端 MCP 管理页面展示。

**响应 data：**

```json
{
  "tools": [
    {
      "name": "probe.disk_usage",
      "description": "获取指定路径的磁盘使用情况",
      "is_builtin": true,
      "source": "builtin",
      "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}
    },
    {
      "name": "get_current_time",
      "description": "获取当前系统时间",
      "is_builtin": false,
      "source": "mcp",
      "parameters": {"type": "object", "properties": {}, "additionalProperties": false}
    }
  ],
  "total": 42,
  "builtin_count": 38,
  "dynamic_count": 0,
  "mcp_count": 4
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `tools` | `array<RegistryToolItem>` | 全部已注册工具列表 |
| `total` | `int` | 工具总数 |
| `builtin_count` | `int` | 内置工具数（代码中注册的 ProbeTool） |
| `dynamic_count` | `int` | 动态工具数（DB 加载的 DynamicMCPTool） |
| `mcp_count` | `int` | MCP Server 工具数（外部 MCP 连接后注册的 ExternalMCPTool） |

**RegistryToolItem 字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `string` | 工具名称（LLM function calling 用） |
| `description` | `string` | 工具功能描述（给 LLM 看） |
| `is_builtin` | `bool` | 是否为内置工具 |
| `source` | `string` | 来源标识：`"builtin"` / `"dynamic"` / `"mcp"` |
| `parameters` | `dict` | JSON Schema 参数定义 |

---

## 10. 审计日志

### 10.1 查询审计日志

```
GET /api/v1/audit?page=1&page_size=20&status=SUCCESS&start_time=2026-04-01T00:00:00&end_time=2026-04-27T23:59:59
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | `int` | `1` | 页码 |
| `page_size` | `int` | `20` | 每页数量（1~100） |
| `status` | `string` | `null` | 过滤：`SUCCESS` / `FAILED` / `TIMEOUT` / `REJECTED` / `BLOCKED` |
| `start_time` | `string` | `null` | 起始时间 ISO 8601 |
| `end_time` | `string` | `null` | 结束时间 ISO 8601 |

返回 `PaginatedData<AuditLogItem>`。

### 10.2 审计统计

```
GET /api/v1/audit/stats
```

返回执行次数统计、状态分布、近期执行记录等。

---

## 11. 推理链路（五段式闭环溯源）

### 11.1 获取推理链路

```
GET /api/v1/reasoning/{session_id}?round_number=1
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `round_number` | `int` | `null` | 指定只返回某轮链路，空则返回全部 |

**响应 data：**

```json
{
  "session_id": "uuid-xxx",
  "total_entries": 5,
  "chain": [
    {"stage": "SENSE", "content": "...", "metadata": "...", "created_at": "..."},
    {"stage": "ANALYZE", "content": "...", "metadata": "...", "created_at": "..."},
    {"stage": "PLAN", "content": "...", "metadata": "...", "created_at": "..."},
    {"stage": "EXECUTE", "content": "...", "metadata": "...", "created_at": "..."},
    {"stage": "OUTPUT", "content": "...", "metadata": "...", "created_at": "..."}
  ]
}
```

### 11.2 推理链路摘要

```
GET /api/v1/reasoning/{session_id}/summary
```

返回统计信息：总轮数、各阶段条目数、时间范围等。

---

## 12. 接口与赛题需求映射

| 接口 | 对应需求 |
|------|---------|
| `POST /api/v1/chat` + `POST /api/v1/chat/stream` | 需求 1（OS 感知）+ 需求 3（安全校验）+ 需求 5（推理溯源） |
| `GET /api/v1/probe/*` | 需求 1（OS 环境深度感知）直查入口 |
| `GET /api/v1/safety/*` | 需求 3（安全校验）+ 需求 4（最小权限执行） |
| `POST /api/v1/execute` | 需求 4（最小权限执行） |
| `GET /api/v1/audit/*` + `GET /api/v1/reasoning/*` | 需求 5（五段式闭环日志 + 审计） |
| `GET/POST /api/v1/tools/*` | 需求 2（MCP 运维插件化） |
| `GET /api/v1/tools/registry` | 需求 2（MCP 插件注册全景展示） |
| `POST /api/v1/safety/injection/scan` | 需求 6（抗提示词注入） |
| `POST /api/v1/safety/config/*` | 需求 3（关键配置写保护） |

---

## 附录：完整端点速查表

```
# 健康检查
GET    /health                         应用存活探针（裸响应）
GET    /api/v1/info                    应用信息 + 模块状态

# OS 探针（只读）
GET    /api/v1/probe/disk              磁盘使用率 + 大文件
GET    /api/v1/probe/processes         进程列表 / 单个详情
GET    /api/v1/probe/network           网络连接 / 接口 / DNS
GET    /api/v1/probe/logs              系统日志（journalctl/tail/grep）

# AI 对话
POST   /api/v1/chat                    非流式对话
POST   /api/v1/chat/stream             SSE 流式对话
GET    /api/v1/chat/history            对话历史

# 会话管理
POST   /api/v1/sessions                创建会话
GET    /api/v1/sessions                会话列表（分页）
GET    /api/v1/sessions/{id}           会话详情
DELETE /api/v1/sessions/{id}           删除会话

# 安全层
GET    /api/v1/safety/status           安全层总览
POST   /api/v1/safety/validate         单条命令安全校验
POST   /api/v1/safety/validate/batch   批量命令安全校验
POST   /api/v1/safety/execute          安全执行命令
POST   /api/v1/safety/config/baseline  采集配置基线
POST   /api/v1/safety/config/scan      扫描配置变更
POST   /api/v1/safety/config/check-write 写操作预检
GET    /api/v1/safety/config/paths     受保护路径列表
POST   /api/v1/safety/injection/scan   提示词注入检测
GET    /api/v1/safety/injection/stats  防护盾统计

# 命令执行
POST   /api/v1/execute                 命令执行（含 dry_run）

# 配置管理
GET    /api/v1/config                  全部配置
GET    /api/v1/config/llm              LLM 配置
PUT    /api/v1/config                  更新配置
DELETE /api/v1/config/{key}            删除配置键
POST   /api/v1/config/reset-all        重置所有配置
POST   /api/v1/config/detect           自动探测协议

# 动态工具
GET    /api/v1/tools                   动态工具列表
GET    /api/v1/tools/registry           注册中心工具全景（内置+动态+MCP）
POST   /api/v1/tools                   注册动态工具
GET    /api/v1/tools/{id}              工具详情
PUT    /api/v1/tools/{id}              更新工具
DELETE /api/v1/tools/{id}              删除工具
POST   /api/v1/tools/{id}/test         测试工具

# 审计日志
GET    /api/v1/audit                   审计日志查询（分页）
GET    /api/v1/audit/stats             审计统计

# 推理链路
GET    /api/v1/reasoning/{session_id}         推理链路
GET    /api/v1/reasoning/{session_id}/summary 推理摘要
```

---

> 最后更新：2026-04-29
