# DevOps Agent - 运维智能体
# 基于 nanoclaw-py 改造

## 目录结构
```
devops-agent/
├── pyproject.toml
├── .env.example          # 环境变量模板（复制为 .env 填入实际值）
├── .gitignore
├── data/                 # SQLite 数据库文件（运行时自动创建）
├── src/
│   └── devops_agent/
│       ├── __init__.py   # 包初始化，版本号
│       ├── main.py       # FastAPI 入口：uvicorn 启动点 + 事件钩子（建表等）
│       ├── config.py     # Pydantic Settings：读取 .env，全局配置对象
│       │
│       ├── api/          # API 层：FastAPI 路由
│       │   ├── __init__.py
│       │   ├── deps.py   # 依赖注入：get_db, get_current_user, get_settings
│       │   ├── router_chat.py      # POST /chat (SSE流式) + WS /ws/chat
│       │   ├── router_probe.py     # GET /probe/{type} (直查探针)
│       │   ├── router_sessions.py  # sessions CRUD
│       │   ├── router_audit.py     # GET /audit-logs 查询
│       │   └── router_auth.py      # POST /auth/login 等
│       │
│       ├── schemas/      # Pydantic 请求/响应模型
│       │   ├── __init__.py
│       │   ├── request.py  # ChatRequest, SessionCreate, AuthLogin
│       │   ├── response.py # ChatResponse, ProbeResponse, AuditLogItem, Error
│       │   └── enums.py    # AuditPhase, SecurityResult 枚举
│       │
│       ├── db/           # 数据访问层
│       │   ├── __init__.py
│       │   ├── connection.py  # aiosqlite 连接池管理 + 自动建表
│       │   ├── models.py      # dataclass: Session, Message, AuditLog, Config, State
│       │   ├── sessions.py    # SessionRepository
│       │   ├── messages.py    # MessageRepository
│       │   ├── audit.py       # AuditLogRepository
│       │   └── config.py      # ConfigRepository
│       │
│       ├── agent/        # Agent 核心引擎（改造自 nanoclaw-py）
│       │   ├── __init__.py
│       │   ├── core.py   # 主循环：接收→感知→推理→校验→执行→响应
│       │   ├── llm_client.py  # 双协议 LLM 客户端（OpenAI/Anthropic 兼容）
│       │   └── context.py     # 对话上下文管理（历史消息、压缩、窗口）
│       │
│       ├── tools/        # MCP 运维工具集（@tool 注册）
│       │   ├── __init__.py
│       │   ├── registry.py    # 工具注册中心（MCP server 封装）
│       │   ├── tool_system_probe.py  # @tool system_probe（Agent 调用的探针入口）
│       │   ├── tool_execute.py       # @tool execute_command（安全执行入口）
│       │   └── tool_cleanup.py       # @tool cleanup_files（清理操作示例）
│       │
│       ├── safety/       # 安全护栏子系统
│       │   ├── __init__.py
│       │   ├── validator.py  # 安全校验器（路径保护+文件检测+权限审查）
│       │   ├── executor.py   # 最小权限执行引擎（devops-runner + 白名单）
│       │   ├── rules.py      # 内置规则库（保护路径列表、危险模式正则）
│       │   └── anti_injection.py  # 抗提示词注入（MVP 可选）
│       │
│       ├── probe/        # OS 探针模块
│       │   ├── __init__.py
│       │   ├── base.py      # 探针基类（超时、错误处理统一封装）
│       │   ├── disk.py      # probe.disk_usage() + large_files()
│       │   ├── process.py   # probe.process_list()
│       │   ├── network.py   # probe.network_connections()
│       │   └── logs.py      # probe.system_logs()
│       │
│       └── memory/        # 会话记忆管理（保留 nanoclaw-py）
│           ├── __init__.py
│           └── manager.py  # 对话归档、上下文持久化
│
├── tests/                # TDD 测试
│   ├── __init__.py
│   ├── conftest.py       # pytest fixtures（测试DB、mock LLM、测试客户端）
│   ├── test_safety_validator.py   # 安全校验器 8 用例
│   ├── test_executor.py           # 执行引擎 4 用例
│   ├── test_probe.py              # 探针模块 5 用例
│   ├── test_api_chat.py           # POST /chat 集成测试
│   └── test_agent_core.py         # Agent 核心循环集成测试
│
├── scripts/              # 辅助脚本
│   ├── init_db.py        # 手动初始化数据库
│   └── create_user.py    # 创建管理员账户
│
└── docs/                 # 文档
    ├── README.md              # 文档索引
    ├── deployment-guide.md    # 完整部署与使用指南（生产环境必读）
    ├── architecture-decisions.md  # 架构决策记录
    ├── selinux-policy-design.md   # SELinux 策略设计
    ├── backend-gap-analysis.md    # 后端功能缺口分析
    └── tui-usage-guide.md         # TUI 终端客户端指南
```

> **首次部署？** 生产环境完整部署流程请阅读 [`docs/deployment-guide.md`](docs/deployment-guide.md)，包含系统要求、麒麟V11环境准备、systemd服务化、配置详解和故障排查。

## 快速开始（开发环境）

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 配置环境
cp .env.example .env
# 编辑 .env 填入你的 LLM API Key

# 4. 初始化数据库（自动建表）
python -m scripts.init_db

# 5. 启动服务
uvicorn devops_agent.main:app --reload --host 0.0.0.0 --port 8000

# 6. 访问 Swagger 文档
open http://localhost:8000/docs
```

## 开发模式
- 后端优先 TDD：先写测试 → 再写实现 → 全绿再下一步
- 第一阶段目标：`curl POST /chat` 能跑通完整链路
