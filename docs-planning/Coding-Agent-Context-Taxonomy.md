# Coding Agent 上下文体系完整指南

> 本文档系统性地梳理了一个 Coding Agent 在执行任务时所需要的各类上下文信息。

---

## 一、项目记忆 (Project Memory)

项目记忆是 Agent 在整个项目生命周期中积累的持久化知识。

### 1.1 决策历史 (Decision Log)
| 类型 | 说明 | 示例 |
|------|------|------|
| 技术选型决策 | 架构、框架、工具的选择理由 | "采用 PostgreSQL 而非 MySQL，因需要 JSONB 支持" |
| 设计模式决策 | 代码组织的模式选择 | "使用 Repository 模式隔离数据访问" |
| 权衡取舍记录 | 性能 vs 可维护性的取舍 | "为支持实时协作，引入 WebSocket 复杂度" |

### 1.2 问题解决记录 (Solution Knowledge Base)
```
问题 → 原因 → 解决方案 → 验证方式
```
- **历史 bug 及修复方案**：避免重复踩坑
- **性能问题及优化记录**：已知瓶颈和解决方案
- **兼容性处理经验**：特定环境/版本的处理方式

### 1.3 项目演进历史 (Evolution History)
- 项目创建时间线
- 重大重构记录
- 依赖升级历史
- 成员贡献摘要

---

## 二、项目规则 (Project Rules)

项目规则定义了代码编写的约束和标准。

### 2.1 代码规范 (Coding Standards)
| 类别 | 内容 | 存储位置建议 |
|------|------|--------------|
| 命名规范 | 变量/函数/类的命名约定 | `docs/coding-standards.md` |
| 代码风格 | 格式化规则、缩进、注释要求 | `.editorconfig`, `.prettierrc` |
| 提交规范 | commit message 格式 | `.github/commit-convention.md` |
| PR 规范 | PR 描述模板、review 要求 | `.github/PULL_REQUEST_TEMPLATE.md` |

### 2.2 架构规则 (Architecture Rules)
```
docs/
├── architecture/
│   ├── system-overview.md      # 系统整体架构
│   ├── module-dependencies.md   # 模块依赖关系
│   ├── data-flow.md             # 数据流设计
│   └── decision-records/        # 架构决策记录 (ADR)
```

### 2.3 测试规则 (Testing Rules)
| 规则 | 说明 |
|------|------|
| 覆盖率要求 | 单元测试覆盖率 ≥ 80% |
| 必须测试的场景 | 核心业务逻辑、边界条件、异常处理 |
| 禁止的操作 | 不允许 mock 内部实现 |

### 2.4 安全规则 (Security Rules)
```
SECURITY.md 或 .security/policy.md
├── 敏感信息处理规范
├── 依赖审计策略
├── 权限最小化原则
└── 密钥管理规范
```

---

## 三、技术上下文 (Technical Context)

### 3.1 技术栈全景
```
技术栈全景图
├── 前端框架: React 18 + TypeScript
├── 后端框架: FastAPI + Python 3.11
├── 数据库: PostgreSQL 15 + Redis 7
├── 容器化: Docker + Kubernetes
├── CI/CD: GitHub Actions
└── 云平台: AWS
```

### 3.2 项目结构 (Project Structure)
```
project/
├── src/                    # 源代码
├── tests/                  # 测试代码
├── docs/                   # 文档
├── scripts/                # 脚本工具
├── configs/                # 配置文件
├── .vscode/                # IDE 配置
├── package.json           # 依赖清单
└── README.md              # 项目说明
```

### 3.3 依赖关系 (Dependencies)
| 类型 | 描述 | 示例 |
|------|------|------|
| 直接依赖 | package.json 中的 dependencies | `react`, `fastapi` |
| 开发依赖 | 仅开发环境使用 | `jest`, `eslint` |
| 可选依赖 | 条件性使用 | `sqlite` (仅无 Postgres 时) |
| 冲突依赖 | 版本冲突记录 | `lodash@4` vs `lodash@5` |

---

## 四、业务上下文 (Business Context)

### 4.1 领域知识 (Domain Knowledge)
```
docs/domain/
├── glossary.md             # 业务术语表
├── business-rules.md       # 业务规则文档
├── user-stories.md         # 用户故事
└── process-flows.md        # 业务流程图
```

### 4.2 功能规格 (Feature Specifications)
| 文档 | 内容 |
|------|------|
| 功能清单 | 所有已实现/规划中的功能 |
| 优先级矩阵 | 功能的业务优先级 |
| 里程碑计划 | 版本发布时间表 |

### 4.3 约束条件 (Constraints)
- **法规合规**：GDPR、PCI-DSS 等要求
- **性能指标**：响应时间、并发量、资源限制
- **可用性要求**：SLA 等级

---

## 五、对话上下文 (Conversation Context)

### 5.1 当前任务状态
| 状态 | 说明 |
|------|------|
| 任务目标 | 用户期望的最终结果 |
| 进度追踪 | 已完成/进行中/待处理的步骤 |
| 阻塞点 | 当前遇到的问题 |

### 5.2 历史对话摘要
```
对话历史摘要
├── 用户偏好
│   ├── 偏好语言/框架
│   ├── 沟通风格
│   └── 代码风格偏好
├── 已讨论内容
│   ├── 明确的需求
│   ├── 已否决的方案
│   └── 待确认的问题
└── 上下文窗口
    └── 最近 N 轮对话的核心内容
```

### 5.3 用户模型 (User Model)
| 维度 | 信息 |
|------|------|
| 专业水平 | 初级/中级/高级/专家 |
| 技术栈熟悉度 | 哪些技术熟悉/不熟悉 |
| 偏好设置 | 详细程度、解释风格 |

---

## 六、环境上下文 (Environment Context)

### 6.1 开发环境
```
环境配置
├── 本地开发环境
│   ├── OS: macOS 14 / Ubuntu 22.04 / Windows 11
│   ├── Node.js: v20.x
│   ├── Python: 3.11
│   └── Docker: 24.x
├── 远程开发环境
│   ├── 开发服务器配置
│   └── 访问凭证 (加密存储)
└── IDE 配置
    ├── VSCode extensions
    └── Settings sync
```

### 6.2 部署环境
| 环境 | 用途 | 配置特点 |
|------|------|----------|
| Development | 本地开发 | 详细日志、debug 模式 |
| Staging | 预发布测试 | 生产镜像、数据脱敏 |
| Production | 正式环境 | 性能优化、安全加固 |

### 6.3 工具链 (Toolchain)
```
工具链配置
├── 版本控制: Git
├── 包管理: npm / pip / Maven
├── 构建工具: Webpack / Vite / Make
├── 测试框架: Jest / pytest / Cypress
├── CI/CD: GitHub Actions / Jenkins
└── 监控: Prometheus / Grafana
```

---

## 七、安全上下文 (Security Context)

### 7.1 认证与授权
```
安全配置
├── 认证方式
│   ├── OAuth2 / OIDC
│   ├── JWT 配置
│   └── 多因素认证
├── 授权模型
│   ├── RBAC 角色定义
│   └── 权限矩阵
└── 会话管理
    ├── 过期时间
    └── 安全策略
```

### 7.2 敏感信息处理
| 类型 | 处理方式 |
|------|----------|
| 数据库凭证 | 环境变量 + 密钥管理服务 |
| API 密钥 | 密钥管理服务 (AWS Secrets Manager) |
| 用户数据 | 加密存储 + 访问审计 |
| 日志脱敏 | 敏感字段自动掩码 |

### 7.3 安全扫描规则
- 依赖漏洞扫描：Snyk / Dependabot
- 代码安全扫描：Semgrep / SonarQube
- 秘密检测：GitLeaks / TruffleHog

---

## 八、工具上下文 (Tool Context)

### 8.1 可用工具能力
```
Tools/
├── 文件系统操作
│   ├── read_file / write_to_file / replace_in_file
│   ├── search_content / search_file
│   └── execute_command / delete_file
├── 代码分析与生成
│   ├── 代码补全
│   ├── 重构建议
│   └── 测试生成
├── 外部服务集成
│   ├── 数据库操作
│   ├── API 调用
│   └── 云服务交互
└── 特殊能力
    ├── 多模态理解
    ├── 文档生成
    └── 图表绘制
```

### 8.2 工具使用约束
| 约束 | 说明 |
|------|------|
| 权限限制 | 哪些目录/文件不可访问 |
| 操作限制 | 危险命令黑名单 (rm -rf /) |
| 审批流程 | 特定操作需要人工确认 |
| 审计日志 | 所有操作的完整记录 |

---

## 九、接口上下文 (API Context)

### 9.1 API 规格
```yaml
API Specification:
  version: v2
  base_url: /api/v2
  endpoints:
    - GET /users/{id}
    - POST /users
    - PUT /users/{id}
    - DELETE /users/{id}
  schemas:
    User:
      id: string
      name: string
      email: string
```

### 9.2 集成点
| 外部系统 | 集成方式 | 关键配置 |
|----------|----------|----------|
| Stripe | REST API | API Key + Webhook |
| SendGrid | SMTP/API | API Key |
| S3 | AWS SDK | IAM Role |

---

## 十、质量保障上下文 (Quality Context)

### 10.1 代码质量标准
| 指标 | 阈值 |
|------|------|
| 测试覆盖率 | ≥ 80% |
| 代码重复率 | < 5% |
| 技术债务 | 严重问题 = 0 |
| 代码风格 | 0 warnings |

### 10.2 评审流程
```
Pull Request 流程:
1. 开发者创建 PR
2. 自动化检查 (CI) → 失败阻止合并
3. 代码审查 (至少 1 人 approve)
4. 质量门禁检查
5. 合并到主分支
```

---

## 上下文获取优先级

```
┌─────────────────────────────────────────────────────────┐
│                    高优先级 (必读)                        │
│  • 项目 README.md                                       │
│  • 当前任务相关代码文件                                   │
│  • 项目规则 (coding standards)                          │
│  • 最近对话摘要                                         │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    中优先级 (推荐)                        │
│  • 技术栈文档                                           │
│  • 业务领域知识                                         │
│  • API 规格                                             │
│  • 项目决策记录                                         │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    低优先级 (按需)                        │
│  • 历史 bug 记录                                        │
│  • 环境配置细节                                         │
│  • 安全策略详细                                         │
│  • 监控告警配置                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 子文档索引

每个上下文维度都有独立的详细文档，存放在 `docs-planning/coding-agent-context/` 目录：

| # | 维度 | 子文档路径 | 核心内容 |
|---|------|-----------|----------|
| 01 | 项目记忆 | [coding-agent-context/01-project-memory.md](./coding-agent-context/01-project-memory.md) | ADR 决策记录、问题解决库、演进历史 |
| 02 | 项目规则 | [coding-agent-context/02-project-rules.md](./coding-agent-context/02-project-rules.md) | 命名规范、代码风格、测试规则、安全红线 |
| 03 | 技术上下文 | [coding-agent-context/03-technical-context.md](./coding-agent-context/03-technical-context.md) | 技术栈全景、项目结构、依赖关系图 |
| 04 | 业务上下文 | [coding-agent-context/04-business-context.md](./coding-agent-context/04-business-context.md) | 领域术语、业务规则、功能规格、用户故事 |
| 05 | 对话上下文 | [coding-agent-context/05-conversation-context.md](./coding-agent-context/05-conversation-context.md) | 当前任务状态、历史摘要、用户偏好 |
| 06 | 环境上下文 | [coding-agent-context/06-environment-context.md](./coding-agent-context/06-environment-context.md) | 环境配置、工具链、部署架构 |
| 07 | 安全上下文 | [coding-agent-context/07-security-context.md](./coding-agent-context/07-security-context.md) | 认证授权、敏感数据、安全扫描 |
| 08 | 工具上下文 | [coding-agent-context/08-tool-context.md](./coding-agent-context/08-tool-context.md) | 可用工具、能力边界、危险命令 |
| 09 | 接口上下文 | [coding-agent-context/09-api-context.md](./coding-agent-context/09-api-context.md) | API 设计、端点规范、集成点 |
| 10 | 质量保障 | [coding-agent-context/10-quality-context.md](./coding-agent-context/10-quality-context.md) | 质量指标、测试规范、CI/CD 流程 |

> **索引目录**: [coding-agent-context/README.md](./coding-agent-context/README.md)

---

## 上下文获取优先级

```
┌─────────────────────────────────────────────────────────┐
│                    高优先级 (必读)                        │
│  • 项目 README.md                                       │
│  • 当前任务相关代码文件                                   │
│  • 项目规则 (coding standards)                          │
│  • 最近对话摘要                                         │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    中优先级 (推荐)                        │
│  • 技术栈文档                                           │
│  • 业务领域知识                                         │
│  • API 规格                                             │
│  • 项目决策记录                                         │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    低优先级 (按需)                        │
│  • 历史 bug 记录                                        │
│  • 环境配置细节                                         │
│  • 安全策略详细                                         │
│  • 监控告警配置                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 总结

一个完整的 Coding Agent 上下文体系包含 **10 大维度**：

| # | 维度 | 核心价值 |
|---|------|----------|
| 1 | 项目记忆 | 避免重复工作，传承项目知识 |
| 2 | 项目规则 | 保证一致性和质量 |
| 3 | 技术上下文 | 理解"如何实现" |
| 4 | 业务上下文 | 理解"为什么实现" |
| 5 | 对话上下文 | 保持沟通连贯性 |
| 6 | 环境上下文 | 知道"在什么环境运行" |
| 7 | 安全上下文 | 防范风险 |
| 8 | 工具上下文 | 明确"能做什么" |
| 9 | 接口上下文 | 理解集成点 |
| 10 | 质量保障上下文 | 保持交付标准 |

---

*文档版本: 1.0.0*
*创建时间: 2026-04-29*
