# 06 - 环境上下文 (Environment Context)

> **父文档**: [Coding Agent 上下文体系](../Coding-Agent-Context-Taxonomy.md)  
> **定义**: 代码运行和开发的环境配置信息

---

## 6.1 文档目的

环境上下文确保 Agent 知道代码在哪里运行、如何配置、以及不同环境之间的差异。

---

## 6.2 组成部分

### 6.2.1 环境类型 (Environment Types)

```yaml
environments:
  local:
    name: 本地开发
    purpose: 开发调试
    data: 测试数据
    features:
      debug: true
      hot_reload: true
      verbose_logging: true

  staging:
    name: 预发布
    purpose: 功能验证
    data: 脱敏生产数据
    features:
      debug: false
      hot_reload: false
      verbose_logging: true

  production:
    name: 生产环境
    purpose: 正式服务
    data: 真实用户数据
    features:
      debug: false
      hot_reload: false
      verbose_logging: false
```

### 6.2.2 开发环境配置 (Development Environment)

#### 本地环境

```markdown
## 本地开发环境要求

### 系统要求
- OS: macOS 13+ / Ubuntu 22.04+ / Windows 11 + WSL2
- RAM: ≥ 16GB (推荐 32GB)
- 磁盘: ≥ 50GB 可用空间

### 必需工具
- Node.js: v18.x 或 v20.x (使用 nvm)
- Python: 3.11+ (使用 pyenv)
- Docker: 24.x
- Git: 2.40+

### 开发工具
- IDE: VSCode (推荐) 或 WebStorm / PyCharm
- 数据库客户端: DBeaver / TablePlus
- API 测试: Postman / Insomnia
```

#### 环境变量配置

```bash
# .env.local (不提交到版本控制)
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
REDIS_URL=redis://localhost:6379
JWT_SECRET=your-secret-key-here
```

### 6.2.3 部署环境 (Deployment Environment)

```yaml
deployment:
  production:
    region: ap-east-1
    instances:
      frontend: 2x t3.medium (Auto Scaling)
      backend: 4x t3.large (Auto Scaling)
    database:
      primary: db.r6g.xlarge (PostgreSQL 15)
      replica: 2x Read Replicas
    cache:
      redis: cache.r6g.large (ElastiCache)
    cdn:
      provider: CloudFront
      origins:
        - frontend-static

  staging:
    region: ap-east-1
    instances:
      frontend: 1x t3.small
      backend: 2x t3.small
    database:
      primary: db.t3.medium
```

### 6.2.4 工具链配置 (Toolchain)

| 类别 | 工具 | 用途 |
|------|------|------|
| 版本控制 | Git | 代码管理 |
| 包管理 | npm / pip | 依赖管理 |
| 构建工具 | Vite / Make | 编译打包 |
| 测试框架 | Jest / pytest | 自动化测试 |
| CI/CD | GitHub Actions | 持续集成 |
| 监控 | Prometheus + Grafana | 性能监控 |
| 日志 | ELK Stack | 日志收集 |
| 容器 | Docker | 运行环境 |

---

## 6.3 存储规范

```
docs/coding-agent-context/
├── 06-environment-context/
│   ├── README.md                    # 本文档 (索引)
│   ├── environments/
│   │   ├── local-setup.md            # 本地环境配置
│   │   ├── staging-config.md         # 预发布环境
│   │   └── production-config.md      # 生产环境
│   ├── toolchain/
│   │   ├── development-tools.md      # 开发工具
│   │   ├── ci-cd-pipeline.md         # CI/CD 配置
│   │   └── monitoring.md             # 监控告警
│   └── .env.example                  # 环境变量模板
```

---

## 6.4 环境切换指南

```bash
# 查看当前环境
echo $APP_ENV

# 切换环境
export APP_ENV=staging

# 验证环境配置
npm run env:verify
```

### 环境一致性保证

| 机制 | 说明 |
|------|------|
| Docker | 本地与生产环境使用相同镜像 |
| 环境变量 | 使用 .env 文件统一管理 |
| 配置中心 | Consul / Apollo 管理运行时配置 |
| 基础设施即代码 | Terraform 管理云资源 |

---

## 6.5 与其他上下文的关系

```
环境上下文
    │
    ├──→ 支撑: 技术上下文 (技术依赖特定环境)
    │
    ├──→ 影响: 安全上下文 (不同环境不同安全级别)
    │
    ├──→ 依赖: 工具上下文 (工具在环境中运行)
    │
    └──→ 约束: 质量保障 (环境决定可用的测试方式)
```

---

*文档版本: 1.0.0*  
*创建时间: 2026-04-29*  
*负责维度: 环境上下文*
