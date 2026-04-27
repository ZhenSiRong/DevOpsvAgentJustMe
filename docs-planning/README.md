# 规划层文档

> 比赛评审文档，按 `01` → `09` 顺序阅读，从业务目标到设计决策形成完整推导链。

---

## 阅读顺序

```
01 业务目标 ──→ 02 功能清单 ──→ 03 核心流程
     │                │               │
     ↓                ↓               ↓
04 数据模型 ←── 05 接口契约 ←── 06 技术栈选型
     │                │               │
     └──────── 07 架构设计 ←─────────┘
                   │
                   ↓
            08 开发规范
                   │
                   ↓
            09 设计文档汇总
```

| 序号 | 文档 | 阅读理由 |
|------|------|---------|
| **01** | [业务目标](01-business-goals.md) | 先理解"为什么做这个项目"——场景、痛点、四大业务目标 |
| **02** | [功能清单](02-functional-requirements.md) | 再看"要做什么"——功能点与赛题评分权重对照 |
| **03** | [核心流程](03-core-workflow.mmd) | 理解"怎么做"——对话交互时序、五段式推理链路 |
| **04** | [数据模型](04-data-model.md) | 数据层设计——Pydantic Schema、ORM、表关系 |
| **05** | [接口契约](05-api-contract.md) | 接口层设计——RESTful API、SSE 流式、WebSocket、错误码 |
| **06** | [技术栈选型](06-tech-stack.md) | 技术决策——为什么选 Vue 3 + FastAPI + SQLite |
| **07** | [架构设计](07-architecture.mmd) | 全局架构——系统分层、组件关系、部署视图 |
| **08** | [开发规范](08-development-guide.md) | 工程实践——TDD、代码规范、Git 流程 |
| **09** | [设计文档汇总](09-design-summary.mmd) | 设计决策索引——关键决策记录与版本历史 |

---

## 每份文档的核心内容速查

### 01 业务目标
- 企业级数据中心运维痛点
- 四大业务目标：降低门槛、环境感知、安全护栏、国产化适配
- 隐含非功能性需求：可靠性、可追溯性、领域适应性

### 02 功能清单
- 功能点与赛题需求映射表
- 评分权重对照

### 03 核心流程
- 用户输入 → OS 感知 → 安全校验 → 工具执行 → 响应生成的完整时序
- 五段式审计日志：received → sense → inference → security_check → execution → response_ready

### 04 数据模型
- Request/Response Pydantic Schema
- SQLite ORM 模型（Session、Message、AuditLog、Config）
- 模型关系图 + 关键设计决策（audit_trail 双存储、tool_calls JSON 存储）

### 05 接口契约
- 5 组 RESTful API：对话、探针、会话 CRUD、审计日志、认证
- WebSocket 实时推送接口
- 统一错误格式 + 错误码分类

### 06 技术栈选型
- 表现层：Vue 3 + Vite + Tailwind CSS
- 业务逻辑层：FastAPI + Uvicorn + Python 3.12
- 数据访问层：SQLite + aiosqlite
- 各组件选型理由 + 备选方案

### 07 架构设计
- 系统分层架构图
- B/S 架构组件关系
- 龙芯 loongarch64 适配说明

### 08 开发规范
- 开发模式总览
- TDD 实践：后端骨架 + 核心链路测试
- 代码规范与 Git 流程

### 09 设计文档汇总
- 设计决策记录（ADR）索引
- 文档版本历史

---

*规划层文档由团队 A、B 共同维护 | 最后更新：2026-04-27*
