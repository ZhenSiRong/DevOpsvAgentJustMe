# Brainstorm：用户动态添加 MCP Tool 方案

## 现状回顾

当前已有基础：
- `ToolRegistry` 单例 + `MCPTool` 基类
- 10 个内置工具静态注册
- `get_tool_definitions()` 生成 LLM function calling schema
- 安全校验器、审计日志、最小权限执行器已就绪

目标：用户在**运行时**（不重启服务、不修改代码）注册新工具。

---

## 方案对比

| 方案 | 描述 | 优点 | 缺点 | 适合场景 |
|------|------|------|------|----------|
| A. 外部 MCP 服务器 | 连接独立 MCP Server（stdio/SSE），走标准 MCP 协议 | 生态兼容、进程隔离、标准协议 | 需进程管理、龙芯兼容性待验证、运维复杂 | 复用现有 MCP 生态工具 |
| B. Shell 命令包装器 | 用户配置 name/description/command，Agent 用 subprocess 执行 | 最简单、零代码、运维场景天然匹配 | 功能受限、命令注入风险需严控 | 自定义系统检查脚本 |
| C. Python 代码上传 | 用户上传 .py 文件实现 MCPTool 基类，动态 import | 功能最强、灵活 | 安全风险极高（exec/import）、沙箱复杂 | 不推荐 |
| D. HTTP 工具 | 用户注册 URL + method + schema，Agent 用 httpx 调用 | 易集成内部平台、无代码、可跨语言 | 依赖外部服务可用性 | 集成监控/告警/CMDB 平台 |

**推荐：B + D 混合为主，A 作为扩展兼容层。**

理由：
1. DevOps 场景下，80% 的自定义工具是 "跑一个脚本/命令"
2. HTTP 工具适合对接现有内部系统（Prometheus/Zabbix/CMDB）
3. 外部 MCP Server 兼容性好但运维成本高，作为进阶能力保留

---

## 数据模型

```sql
CREATE TABLE dynamic_tools (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,     -- 工具名（LLM function name）
    description TEXT NOT NULL,             -- 工具描述（给 LLM 看）
    tool_type   TEXT NOT NULL,             -- shell | http | mcp_stdio | mcp_sse
    config      TEXT NOT NULL,             -- JSON 配置（根据 type 不同结构）
    schema      TEXT NOT NULL,             -- OpenAI function schema JSON
    is_active   INTEGER DEFAULT 1,         -- 是否启用
    created_by  TEXT,                      -- 创建者标识
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### config 结构示例

**shell 类型：**
```json
{
  "command": "systemctl status {{service}}",
  "timeout": 30,
  "shell": "/bin/bash",
  "working_dir": "/tmp"
}
```

**http 类型：**
```json
{
  "url": "http://prometheus:9090/api/v1/query",
  "method": "GET",
  "headers": {"Authorization": "Bearer {{token}}"},
  "body_template": null,
  "query_params": {"query": "{{promql}}"},
  "timeout": 10
}
```

**mcp_stdio 类型：**
```json
{
  "command": "python3",
  "args": ["/opt/tools/my_mcp_server.py"],
  "env": {"API_KEY": "xxx"}
}
```

---

## 架构改动

```
┌─────────────────────────────────────────────────────────────┐
│  前端 / TUI                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Tools 管理页 │  │ 工具注册表单 │  │ 内置+动态工具列表   │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────┘  │
└─────────┼────────────────┼──────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│  后端 API 层                                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ POST /tools │  │ GET /tools  │  │ POST /tools/{id}/test│  │
│  │ 注册工具    │  │ 列出工具    │  │ 测试工具            │  │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────┘  │
└─────────┼────────────────┼──────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│  工具执行层                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ ToolRegistry│  │DynamicTool  │  │ MCPTool 基类（已有）│  │
│  │ 运行时注册  │◄─┤ 分发执行    │◄─┤ 内置工具            │  │
│  │ 合并 schema │  │ shell/http  │  │                     │  │
│  └──────┬──────┘  └─────────────┘  └─────────────────────┘  │
└─────────┼────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│  Agent 引擎                                                  │
│  每次对话前：从 DB 加载 active 动态工具 → 合并到 schema      │
│  发送给 LLM                                                 │
└─────────────────────────────────────────────────────────────┘
```

### 涉及文件改动

| 文件 | 动作 | 说明 |
|------|------|------|
| `api/routes/tools.py` | 新增 | 动态工具 CRUD + test 端点 |
| `tools/dynamic.py` | 新增 | DynamicTool 分发器（shell/http/mcp） |
| `tools/registry.py` | 改造 | `register_dynamic_tool()` / `unregister()` / 从 DB 加载 |
| `agent/core.py` | 改造 | `run_agent()` 开头刷新工具列表 |
| `db/migrations/` | 新增 | dynamic_tools 表迁移 |
| `security/validator.py` | 改造 | 动态 shell 命令额外校验规则 |
| `cli/app.py` | 可选 | TUI 新增 /tools 命令浏览工具列表 |

---

## 安全设计

动态工具 = 用户输入的代码/命令，风险极高。必须多层防御：

### 1. 注册时校验
- **名称规范**：只允许 `a-z0-9_`，不能以 `_` 开头（防覆盖内置工具）
- **schema 校验**：必须是合法的 JSON Schema
- **命令白名单**：shell 类型命令必须匹配允许的正则（如只允许 `systemctl`、`journalctl`、`df`、`ping` 等已知命令前缀）
- **URL 白名单**：http 类型只允许内网 IP 或指定域名

### 2. 执行时校验
- 走现有的 `safety.validate_command()` 流程
- shell 类型额外检查：禁止 `rm`、`dd`、`mkfs`、`>` 重定向、`curl | bash` 等
- 超时强制：所有动态工具默认 30s，最长 120s
- 沙箱用户：用 `devops-runner` 账户执行（已有）

### 3. 审计
- 所有动态工具调用写入 `audit_log`（已有表）
- 记录：谁创建的工具、谁调用的、参数、结果、耗时

### 4. 隔离
- 动态工具与内置工具在 registry 中区分标识
- 前端显示时标注 "自定义" 标签
- 支持一键禁用（is_active=0）

---

## API 设计

```http
# 注册 Shell 工具
POST /api/v1/tools
{
  "name": "check_service",
  "description": "检查指定系统服务的状态",
  "tool_type": "shell",
  "config": {
    "command": "systemctl status {{service_name}}",
    "timeout": 15
  },
  "schema": {
    "type": "object",
    "properties": {
      "service_name": {"type": "string", "description": "服务名，如 nginx"}
    },
    "required": ["service_name"]
  }
}

# 注册 HTTP 工具
POST /api/v1/tools
{
  "name": "query_prometheus",
  "description": "查询 Prometheus 指标",
  "tool_type": "http",
  "config": {
    "url": "http://prometheus:9090/api/v1/query",
    "method": "GET",
    "query_params": {"query": "{{promql}}"},
    "timeout": 10
  },
  "schema": {
    "type": "object",
    "properties": {
      "promql": {"type": "string", "description": "PromQL 查询语句"}
    },
    "required": ["promql"]
  }
}

# 列出所有工具（内置 + 动态）
GET /api/v1/tools
# 返回：{ "builtin": [...], "dynamic": [...] }

# 测试工具（不经过 LLM，直接执行）
POST /api/v1/tools/check_service/test
{"service_name": "sshd"}
```

---

## 实现优先级

| 阶段 | 内容 | 预计工作量 |
|------|------|------------|
| P1 | DB 表 + `tools/dynamic.py` Shell 执行器 + Registry 改造 + `/tools` API | 1 人天 |
| P2 | HTTP 工具执行器 + URL 白名单校验 | 0.5 人天 |
| P3 | 前端 Tools 管理页面（注册表单 + 列表 + 测试） | 队友负责 |
| P4 | 外部 MCP Server 兼容（stdio/SSE） | 2 人天（进阶） |

---

## 关键决策点

1. **是否允许参数模板（Jinja2）？** 如 `command: "systemctl status {{service}}"`
   - 建议：P1 先用简单字符串替换，P2 引入 Jinja2（但限制沙箱，禁止危险 filter）

2. **动态工具重启后是否保留？**
   - 必须保留。数据存 SQLite，服务启动时从 DB 加载到 Registry

3. **内置工具能否被动态工具覆盖？**
   - 禁止。名称冲突时注册失败，或动态工具加 `dyn_` 前缀

4. **是否需要工具版本/回滚？**
   - P1 不做，P3 可考虑软删除 + 历史记录
