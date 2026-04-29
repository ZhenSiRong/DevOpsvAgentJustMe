# 09 - 接口上下文 (API Context)

> **父文档**: [Coding Agent 上下文体系](../Coding-Agent-Context-Taxonomy.md)  
> **定义**: 项目的 API 设计、内部接口和外部集成

---

## 9.1 文档目的

接口上下文帮助 Agent 理解系统内部和外部的数据交互方式，确保代码变更不会破坏接口契约。

---

## 9.2 组成部分

### 9.2.1 API 架构 (API Architecture)

```yaml
api:
  version: v2
  base_url: /api/v2
  protocol: HTTPS
  format: JSON
  auth: Bearer Token (JWT)
  
  design:
    style: RESTful
    versioning: URL Path
    pagination: cursor-based
    
  conventions:
    dates: ISO 8601
    errors: RFC 7807 Problem Details
    ids: UUID v4
```

### 9.2.2 API 端点规范 (Endpoint Specifications)

#### 资源: Users

```yaml
/users:
  GET:
    summary: 列出用户
    parameters:
      - name: page
        type: integer
        default: 1
      - name: limit
        type: integer
        default: 20
    responses:
      200:
        schema:
          type: object
          properties:
            data: array[User]
            pagination: Pagination

  POST:
    summary: 创建用户
    body: CreateUserRequest
    responses:
      201: User
      400: Error

/users/{id}:
  GET:
    summary: 获取用户详情
    parameters:
      - name: id
        type: string
        in: path
    responses:
      200: User
      404: Error

  PUT:
    summary: 更新用户
    body: UpdateUserRequest
    responses:
      200: User

  DELETE:
    summary: 删除用户
    responses:
      204: No Content
```

#### 响应格式

```json
// 成功响应
{
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-04-29T17:00:00Z"
  }
}

// 错误响应 (RFC 7807)
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "The email field is required",
  "instance": "/users",
  "errors": [
    { "field": "email", "message": "required" }
  ]
}
```

### 9.2.3 数据模型 (Data Models)

```yaml
# Schema 定义

User:
  id: string (uuid)
  email: string (email format)
  name: string (1-100 chars)
  role: enum [admin, user, guest]
  created_at: datetime
  updated_at: datetime

CreateUserRequest:
  email: string (required, valid email)
  name: string (required, 1-100 chars)
  password: string (required, min 8 chars)
  
UpdateUserRequest:
  email: string (optional)
  name: string (optional)
  role: enum (optional, admin only)
```

### 9.2.4 集成点 (Integration Points)

| 外部系统 | 集成方式 | 协议 | 关键配置 |
|----------|----------|------|----------|
| Stripe | Payment API | REST/HTTPS | API Key + Webhook |
| SendGrid | Email API | REST/HTTPS | API Key |
| AWS S3 | SDK | HTTPS | IAM Role |
| Slack | Webhook | HTTPS | Webhook URL |
| GitHub | OAuth + API | OAuth2/HTTPS | Client ID/Secret |

#### Webhook 配置

```yaml
webhooks:
  payment.completed:
    url: https://api.example.com/webhooks/stripe
    events:
      - payment_intent.succeeded
      - payment_intent.failed
    retry:
      max_attempts: 3
      backoff: exponential
      
  user.action:
    url: https://api.example.com/webhooks/github
    events:
      - push
      - pull_request
    security:
      verify_signature: true
```

---

## 9.3 存储规范

```
docs/coding-agent-context/
├── 09-api-context/
│   ├── README.md                    # 本文档 (索引)
│   ├── design/
│   │   ├── api-conventions.md        # API 设计规范
│   │   ├── versioning-strategy.md   # 版本策略
│   │   └── error-handling.md        # 错误处理
│   ├── endpoints/
│   │   ├── users-api.md             # 用户 API
│   │   ├── resources-api.md         # 资源 API
│   │   └── webhooks-api.md          # Webhook API
│   ├── schemas/
│   │   ├── request-schemas.md       # 请求 Schema
│   │   └── response-schemas.md     # 响应 Schema
│   └── integrations/
│       ├── stripe-integration.md     # Stripe 集成
│       ├── aws-integration.md       # AWS 集成
│       └── github-integration.md    # GitHub 集成
```

---

## 9.4 API 设计原则

| 原则 | 说明 |
|------|------|
| RESTful | 使用标准 HTTP 方法和状态码 |
| 幂等性 | 多次请求结果一致 |
| 向后兼容 | 新增可选字段，不删除已有字段 |
| 文档同步 | 代码变更时更新 API 文档 |

---

## 9.5 与其他上下文的关系

```
接口上下文
    │
    ├──→ 依赖: 技术上下文 (HTTP 框架、序列化)
    │
    ├──→ 反映: 业务上下文 (API 暴露业务能力)
    │
    ├──→ 约束: 安全上下文 (认证、授权)
    │
    └──→ 验证: 质量保障 (API 测试)
```

---

*文档版本: 1.0.0*  
*创建时间: 2026-04-29*  
*负责维度: 接口上下文*
