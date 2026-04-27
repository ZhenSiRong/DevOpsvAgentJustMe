# 08 开发指南

> DevOps Agent 后端开发规范与项目结构
> 适用阶段：Phase 4（可靠性增强）
> 最后更新：2026-04-27

---

## 1. 项目概述

DevOps Agent 是一个面向国产化环境（龙芯 loongarch64 + 麒麟高级服务器版 V11）的运维智能体平台，B/S 架构。当前处于 Phase 4（可靠性增强），核心能力已全部实现：OS 探针、安全校验器、最小权限执行引擎、MCP 工具插件化、推理链路溯源、抗提示词注入。

### 1.1 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 后端框架 | FastAPI + Uvicorn | 异步 ASGI，自动生成 OpenAPI/Swagger |
| 运行时 | Python 3.12.9 | 麒麟 V11 上源码编译 |
| 数据库 | SQLite + aiosqlite | 异步连接池，应用启动自动建表 |
| LLM 接入 | OpenAI SDK + Anthropic SDK | 双协议：OpenAI Chat Completions / Anthropic Messages |
| 前端 | React 18 + Vite + Tailwind CSS | SPA，6 页面，已部署到 VM |
| 通信 | REST API + SSE | SSE 用于流式对话，WebSocket 未实现 |
| 权限 | sudo -u devops-runner | 最小权限执行 |

### 1.2 代码位置

```
devops-agent/
├── src/devops_agent/          # 后端源码根
│   ├── main.py                # FastAPI 应用入口
│   ├── config.py              # 配置管理（.env + DB 覆盖）
│   ├── api/                   # API 层
│   │   ├── main.py            # 路由聚合
│   │   ├── schemas.py         # Pydantic 请求/响应模型
│   │   └── routes/            # 路由模块（10 个）
│   ├── agent/                 # Agent 核心引擎
│   ├── db/                    # 数据访问层
│   ├── llm/                   # LLM 协议适配
│   ├── memory/                # 记忆管理
│   ├── probe/                 # OS 探针（只读）
│   ├── safety/                # 安全层（Phase 2 核心）
│   ├── tools/                 # MCP 工具注册中心
│   └── cli/                   # TUI 命令行界面
├── frontend/                  # React SPA 前端
├── tests/                     # 测试目录
│   ├── test_*.py             # 单元/集成测试
│   └── delivery/             # 交付测试脚本集
├── data/                      # SQLite 数据库文件
├── requirements.txt           # Python 依赖
└── pyproject.toml             # 项目配置
```

---

## 2. 数据库表结构

应用启动时由 `db/connection.py` 自动执行建表 SQL，共 8 张核心表 + 2 张保留表：

| 表名 | 说明 | 核心字段 |
|------|------|---------|
| `sessions` | 会话 | id(PK), title, user_id, created_at, updated_at |
| `messages` | 对话消息 | id(PK), session_id(FK), role, content, tool_calls, audit_trail |
| `audit_logs` | 审计日志 | id, session_id, phase, content, status, security_result, command, exit_code |
| `configs` | 全局配置覆盖 | key(PK), value, updated_at |
| `conversation_state` | 对话状态 | session_id(PK), context_summary, total_turns |
| `memories` | 跨会话记忆 | id, type(fact/summary/preference/system_state), content, importance |
| `reasoning_chains` | 推理链路 | id, session_id, round_number, stage(SENSE/ANALYZE/PLAN/EXECUTE/OUTPUT) |
| `dynamic_tools` | 动态工具 | id, name, description, tool_type, config, schema_json, is_active |
| `scheduled_tasks` | 定时任务（保留） | id, name, cron_expr, command, enabled |
| `task_run_logs` | 任务运行日志（保留） | id, task_id(FK), status, output, error |

---

## 3. 开发环境

### 3.1 本地开发（Windows）

```bash
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器（本地调试用，VM 上也要跑一遍）
uvicorn src.devops_agent.main:app --reload --host 0.0.0.0 --port 8000
```

### 3.2 测试环境（VM — 麒麟 V11）

- **VM IP**：`192.168.187.128`（NAT 模式，DHCP 分配，动态变化时需重新确认）
- **连接**：SSH root@192.168.187.128，密钥认证
- **Python**：`/usr/bin/python3` → Python 3.12.9（源码编译）
- **项目路径**：`/root/devops-agent/`
- **硬性规则**：所有代码开发后的构建、测试、运行验证**必须在 VM 上进行**
- **代码同步**：Windows 本地写代码 → SCP 传到 VM → SSH 执行安装/测试
- **SSH 终端**：用 `cmd /c` 执行 SSH 命令，**禁止用 PowerShell**（吞 stderr/stdout）

```bash
# VM 上启动
source /root/devops-agent/venv/bin/activate  # 如有 venv
cd /root/devops-agent
python3 -m uvicorn src.devops_agent.main:app --host 0.0.0.0 --port 8000
```

### 3.3 前端开发

```bash
cd frontend
npm install
npm run dev        # 本地开发
npm run build      # 生产构建（输出到 dist/）
```

构建产物通过 SCP 上传到 VM `/root/devops-agent/frontend/dist/`，由 FastAPI `StaticFiles` 托管。

---

## 4. 模块开发规范

### 4.1 新增 API 路由

1. 在 `src/devops_agent/api/routes/` 下新建 `xxx.py`
2. 定义 `APIRouter(prefix="/api/v1/xxx")`
3. 在 `src/devops_agent/api/main.py` 中 `app.include_router(xxx_router)`
4. **必须**添加 `response_model=APIResponse`（健康检查除外）
5. **必须**添加 `summary` 参数用于 Swagger 文档

示例：

```python
from fastapi import APIRouter
from ..schemas import APIResponse

router = APIRouter(prefix="/api/v1/example", tags=["示例模块"])

@router.get("", response_model=APIResponse, summary="示例接口")
async def example() -> APIResponse:
    return APIResponse(data={"key": "value"})
```

### 4.2 新增数据库表

1. 在 `src/devops_agent/db/connection.py` 的 `CREATE_TABLES_SQL` 中添加 `CREATE TABLE IF NOT EXISTS`
2. 在 `src/devops_agent/db/models.py` 中定义对应的 Pydantic/dataclass 模型
3. 在 `src/devops_agent/db/` 下新建 `xxx.py` 写 CRUD 函数
4. **必须**添加索引

### 4.3 新增安全规则

在 `src/devops_agent/safety/rules.py` 中：

- 路径保护规则 → `PROTECTED_PATHS`
- 敏感文件规则 → `SENSITIVE_FILES`
- 危险模式规则 → `DANGEROUS_PATTERNS`
- 只读白名单 → `READONLY_COMMANDS`

### 4.4 新增 MCP 工具

1. 继承 `MCPTool` 基类实现工具逻辑
2. 在 `src/devops_agent/tools/registry.py` 中注册
3. 前端 `Settings` 页面会自动展示内置工具列表

---

## 5. 测试策略

### 5.1 测试目录结构

```
tests/
├── test_probe.py              # 探针单元测试
├── test_safety_phase2.py      # 安全层测试
├── test_api.py                # API 集成测试
└── delivery/                  # 交付测试（交付前最终验证）
    ├── test_base.py           # 测试框架基类
    ├── test_health_probe.py   # 健康检查 + OS 探针
    ├── test_sessions_chat.py  # 会话管理 + 对话
    ├── test_safety_api.py     # 安全层 API
    ├── test_config_tools.py   # 配置 + 工具管理
    ├── test_audit_reasoning.py # 审计 + 推理链路
    └── run_all_delivery_tests.py # 统一运行入口
```

### 5.2 交付测试

交付前**必须在 VM 上**运行交付测试：

```bash
cd /root/devops-agent/tests/delivery
python3 run_all_delivery_tests.py
```

- 55 个用例，预期全部通过
- 总用时约 50 秒（含 LLM 调用超时等待）
- 输出含 `[START]` / `[END]` / `[TOTAL]` 时间统计

### 5.3 测试原则

| 模块 | 测试类型 | 说明 |
|------|---------|------|
| 安全校验器 | 单元测试 + 交付测试 | 高危代码，必须全覆盖 |
| 执行引擎 | 单元测试 + 交付测试 | 涉及系统命令执行 |
| 探针解析器 | 单元测试 | 不同发行版输出格式可能不同 |
| 路由层 | 交付测试 | HTTP 端到端 |
| LLM 接入 | 手动测试 | 依赖外部服务，不做自动化断言 |

---

## 6. 配置管理

### 6.1 配置分层

```
.env 默认值 → DB configs 表覆盖值 → 运行时合并
```

- `.env`：提供默认值，**不**通过 API 修改
- DB `configs` 表：存储用户覆盖值，通过 `/api/v1/config` 管理
- `get_llm_runtime_config()`：合并后读取

### 6.2 环境变量清单

```bash
# LLM 配置
LLM_PROTOCOL=openai              # openai | anthropic
LLM_BASE_URL=https://api.xxx.com
LLM_API_KEY=sk-xxx
LLM_MODEL=MiniMax-M2.1
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096

# Anthropic 协议（可选）
ANTHROPIC_BASE_URL=
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=

# 安全配置
SAFE_EXEC_USER=devops-runner     # 最小权限执行用户
SAFE_EXEC_TIMEOUT=30             # 默认执行超时

# 应用
APP_NAME=devops-agent
LOG_LEVEL=INFO
```

---

## 7. 部署

### 7.1 开发环境启动

```bash
# 方式1：直接启动
python3 -m uvicorn src.devops_agent.main:app --host 0.0.0.0 --port 8000

# 方式2：后台守护
nohup python3 -m uvicorn src.devops_agent.main:app --host 0.0.0.0 --port 8000 > /tmp/devops-agent.log 2>&1 &
```

### 7.2 生产部署要点

1. **HTTPS**：B/S 通信走 HTTPS，内网部署
2. **SELinux**：enforcing 模式不降级，禁止用 permissive 绕过
3. **devops-runner 用户**：必须预先创建，sudo 权限只给白名单命令
4. **日志**：审计日志 append-only，定期归档
5. **前端**：`npm run build` 后 SCP 到 VM，FastAPI `StaticFiles` 托管

---

## 8. 接口开发 Checklist

新增接口时逐一确认：

- [ ] 路由前缀正确（`prefix="/api/v1/xxx"`）
- [ ] 返回 `APIResponse` 包装（健康检查除外）
- [ ] 添加了 `summary` 参数
- [ ] 请求/响应模型定义在 `schemas.py` 或路由文件中
- [ ] 错误处理使用 `HTTPException` 或返回 `APIResponse(code=..., message=...)`
- [ ] 交付测试已覆盖（如适用）
- [ ] Swagger UI (`/docs`) 中可正常展示

---

## 9. 常见问题

### Q: 本地修改后如何同步到 VM？

```bash
# Windows cmd
scp -r devops-agent root@192.168.187.128:/root/
```

### Q: VM IP 变了怎么办？

VM 使用 NAT + DHCP，IP 可能变化。确认方式：

```bash
ssh root@192.168.187.128 "ip addr show | grep 192.168"
```

### Q: 如何确认后端在跑？

```bash
curl http://192.168.187.128:8000/health
```

### Q: 数据库在哪？

```
/root/devops-agent/data/devops_agent.db
```

SQLite 文件，可直接用 `sqlite3` 命令行查看。

---

> 最后更新：2026-04-27
