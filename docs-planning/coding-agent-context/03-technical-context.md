# 03 - 技术上下文 (Technical Context)

> **父文档**: [Coding Agent 上下文体系](../Coding-Agent-Context-Taxonomy.md)  
> **定义**: 项目使用的技术栈及其配置信息

---

## 3.1 文档目的

技术上下文让 Agent 理解项目使用什么技术、如何组织代码、以及各技术之间的关系。

---

## 3.2 组成部分

### 3.2.1 技术栈全景 (Technology Stack)

```yaml
# 技术栈概览

frontend:
  framework: React 18
  language: TypeScript 5.x
  ui_library: Ant Design 5.x
  state_management: Zustand
  routing: React Router 6

backend:
  framework: FastAPI
  language: Python 3.11
  orm: SQLAlchemy 2.0
  api_doc: OpenAPI 3.1

database:
  primary: PostgreSQL 15
  cache: Redis 7
  search: Elasticsearch 8

infrastructure:
  container: Docker 24
  orchestration: Kubernetes 1.28
  ci_cd: GitHub Actions
  cloud: AWS
```

### 3.2.2 项目结构 (Project Structure)

```
project-root/
├── frontend/                    # 前端应用
│   ├── src/
│   │   ├── components/          # React 组件
│   │   ├── pages/              # 页面组件
│   │   ├── hooks/              # 自定义 Hooks
│   │   ├── services/           # API 调用
│   │   ├── stores/             # 状态管理
│   │   └── utils/              # 工具函数
│   ├── public/
│   └── package.json
│
├── backend/                     # 后端应用
│   ├── src/
│   │   ├── api/                # API 路由
│   │   ├── core/               # 核心配置
│   │   ├── models/             # 数据模型
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # 业务逻辑
│   │   └── db/                 # 数据库配置
│   └── requirements.txt
│
├── shared/                      # 共享代码
│   ├── types/                  # 共享类型定义
│   └── constants/              # 共享常量
│
├── infrastructure/              # 基础设施
│   ├── docker/
│   ├── k8s/
│   └── terraform/
│
├── docs/                        # 文档
└── README.md
```

### 3.2.3 依赖关系 (Dependencies)

#### 核心依赖图

```
用户请求
    ↓
[React Frontend]
    ↓ HTTP
[FastAPI Backend]
    ↓ SQLAlchemy
[PostgreSQL DB]
    ↓
[Redis Cache]
```

#### 依赖管理文件

| 环境 | 文件 | 工具 |
|------|------|------|
| 前端生产 | `frontend/package.json` | npm |
| 前端开发 | `frontend/package-lock.json` | npm |
| 后端生产 | `backend/requirements.txt` | pip |
| 后端开发 | `backend/requirements-dev.txt` | pip |

### 3.2.4 构建与部署

```yaml
build:
  frontend:
    command: npm run build
    output: frontend/dist
    docker: frontend.Dockerfile
  
  backend:
    command: pip install -r requirements.txt
    output: backend/
    docker: backend.Dockerfile

deployment:
  strategy: rolling-update
  health_check:
    path: /health
    interval: 30s
```

---

## 3.3 存储规范

```
docs/coding-agent-context/
├── 03-technical-context/
│   ├── README.md                    # 本文档 (索引)
│   ├── stack/
│   │   ├── overview.md              # 技术栈总览
│   │   ├── frontend-stack.md
│   │   ├── backend-stack.md
│   │   └── infrastructure-stack.md
│   ├── structure/
│   │   ├── project-tree.md
│   │   └── module-responsibilities.md
│   └── dependencies/
│       ├── dependency-graph.md
│       └── version-matrix.md
```

---

## 3.4 关键配置文件

| 用途 | 文件路径 |
|------|----------|
| 前端配置 | `frontend/vite.config.ts` |
| TypeScript 配置 | `frontend/tsconfig.json` |
| ESLint 配置 | `frontend/.eslintrc.js` |
| 后端配置 | `backend/src/core/config.py` |
| Docker Compose | `infrastructure/docker/docker-compose.yml` |
| CI/CD | `.github/workflows/` |

---

## 3.5 技术约束

```markdown
## 版本约束

- Node.js: ^18.0.0 (使用 nvm 管理)
- Python: 3.11+ (使用 pyenv 管理)
- PostgreSQL: >= 15.0
- Redis: >= 7.0

## 兼容性矩阵

| 浏览器 | 最低版本 |
|--------|----------|
| Chrome  | 90+      |
| Firefox | 90+      |
| Safari  | 14+      |
| Edge    | 90+      |
```

---

## 3.6 与其他上下文的关系

```
技术上下文
    │
    ├──→ 支撑: 项目规则 (代码规范基于技术特性)
    │
    ├──→ 依赖: 环境上下文 (技术需要特定环境运行)
    │
    ├──→ 定义: 接口上下文 (API 技术选型)
    │
    └──→ 服务: 业务上下文 (技术服务于业务需求)
```

---

*文档版本: 1.0.0*  
*创建时间: 2026-04-29*  
*负责维度: 技术上下文*
