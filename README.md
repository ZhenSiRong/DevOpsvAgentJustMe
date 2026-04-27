# DevOps Agent — 运维智能体平台

> 中国软件杯 A2 赛题参赛作品 | 龙芯 loongarch64 + 麒麟高级服务器版 V11

## 项目速览

面向国产化 Linux 生产环境的运维智能体平台。管理员通过自然语言下达运维指令，Agent 自动感知系统环境、执行安全校验、调用 MCP 工具插件完成运维操作，并生成五段式审计日志实现全链路可追溯。

**核心能力**：
- 🧠 自然语言交互 —— 用中文说话即可完成运维
- 🔍 OS 环境深度感知 —— 自动探查磁盘、进程、网络、日志状态
- 🛡️ 安全意图校验 —— 语义级安全判断，避免误操作
- 🔧 MCP 工具插件化 —— 可扩展的运维工具注册中心
- 📝 五段式审计日志 —— 从接收到响应的完整推理链路溯源

**运行环境**：龙芯 loongarch64 / 麒麟 V11 / Python 3.12 / SELinux Enforcing

---

## 文档导航

### 规划层（比赛评审文档）

按顺序阅读，从"为什么"到"怎么做"。

| 序号 | 文档 | 内容 |
|------|------|------|
| 01 | [业务目标](docs-planning/01-business-goals.md) | 项目背景、场景提炼、四大业务目标 |
| 02 | [功能清单](docs-planning/02-functional-requirements.md) | 功能点与赛题评分对照 |
| 03 | [核心流程](docs-planning/03-core-workflow.mmd) | 对话交互时序与五段式推理链路 |
| 04 | [数据模型](docs-planning/04-data-model.md) | Pydantic Schema + ORM + 关系图 |
| 05 | [接口契约](docs-planning/05-api-contract.md) | RESTful API + WebSocket + 错误码 |
| 06 | [技术栈选型](docs-planning/06-tech-stack.md) | 表现层/业务逻辑层/数据访问层选型理由 |
| 07 | [架构设计](docs-planning/07-architecture.mmd) | 系统架构图 + 分层说明 |
| 08 | [开发规范](docs-planning/08-development-guide.md) | 开发模式、TDD 实践、核心链路 |
| 09 | [设计文档汇总](docs-planning/09-design-summary.mmd) | 设计决策索引与版本历史 |

### 工程层（开发文档）

| 文档 | 内容 |
|------|------|
| [快速开始](devops-agent/README.md) | 安装、配置、启动后端 |
| [TUI 使用指南](devops-agent/docs/tui-usage-guide.md) | 终端交互客户端命令与快捷键 |
| [后端功能缺口分析](devops-agent/docs/backend-gap-analysis.md) | 已实现 vs 待实现功能对照 |
| [SELinux 策略设计](devops-agent/docs/selinux-policy-design.md) | 安全策略模块设计 |
| [架构决策记录](devops-agent/docs/architecture-decisions.md) | 关键技术决策记录 |

---

## 快速开始

```bash
# 1. 克隆项目
cd devops-agent

# 2. 安装依赖（麒麟 V11 需 Python 3.12）
pip3 install -r requirements.txt

# 3. 启动后端
PYTHONPATH=src python3 -m uvicorn devops_agent.main:app --host 0.0.0.0 --port 8000

# 4. 启动 TUI 客户端
python3 -m devops_agent.cli
```

完整部署说明见 [devops-agent/README.md](devops-agent/README.md)。

---

## 项目结构

```
DevOpsAgentPlaning/
├── docs-planning/          # 比赛评审文档
├── devops-agent/           # 工程代码 + 开发文档
│   ├── src/                # Python 源码
│   ├── frontend/           # React 前端
│   └── docs/               # 工程文档
├── assets/                 # 图表、截图等静态资源
└── README.md               # 本文档（总入口）
```

---

## 团队

| 角色 | 负责领域 |
|------|---------|
| A | LLM 集成 / 安全层 / MCP 插件 / 项目管理 |
| B | 前端 / 文档 / 测试 / 后端辅助 |

---

*中国软件杯 A2 赛题 | 交付截止：2026-06-30*
