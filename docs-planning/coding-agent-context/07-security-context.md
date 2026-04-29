# 07 - 安全上下文 (Security Context)

> **父文档**: [Coding Agent 上下文体系](../Coding-Agent-Context-Taxonomy.md)  
> **定义**: 项目安全相关的配置、规则和最佳实践

---

## 7.1 文档目的

安全上下文确保 Agent 在任何操作中都遵循安全原则，防范数据泄露和未授权访问。

---

## 7.2 组成部分

### 7.2.1 认证与授权 (Authentication & Authorization)

#### 认证机制

```yaml
auth:
  primary:
    method: OAuth2 + JWT
    issuer: https://auth.example.com
    token_expiry: 3600  # 1 hour
    
  mfa:
    required_for: admin, service_accounts
    methods:
      - totp
      - sms
      - hardware_key
      
  session:
    type: stateless_jwt
    refresh_token_expiry: 604800  # 7 days
```

#### 授权模型 (RBAC)

```markdown
## 角色定义

| 角色 | 权限 |
|------|------|
| super_admin | 所有权限，无限制 |
| tenant_admin | 本租户内完全控制 |
| developer | 读写代码，无生产部署 |
| viewer | 只读访问 |
| guest | 受限只读 |

## 权限矩阵

| 操作 | super_admin | tenant_admin | developer | viewer |
|------|-------------|--------------|-----------|--------|
| 创建资源 | ✅ | ✅ | ✅ | ❌ |
| 删除资源 | ✅ | ✅ | ❌ | ❌ |
| 查看日志 | ✅ | ✅ | ✅ | ❌ |
| 修改配置 | ✅ | 本租户 | ❌ | ❌ |
```

### 7.2.2 敏感信息处理 (Sensitive Data)

```markdown
## 敏感信息分类

### 🔴 极高敏感
- 数据库主密钥 (Master Key)
- 用户密码 (应使用 bcrypt/argon2)
- 支付信息

### 🟠 高敏感
- API 密钥
- OAuth Client Secret
- JWT Secret

### 🟡 中敏感
- 用户邮箱
- IP 地址
- 操作日志

### 🟢 低敏感
- 用户名
- 公开的项目名
- 公开的配置
```

#### 处理规范

```bash
# ✅ 正确做法
export DATABASE_URL=postgresql://user:pass@host/db

# ❌ 禁止做法
DATABASE_URL=postgresql://user:pass@host/db  # 在代码中硬编码
```

### 7.2.3 安全扫描规则 (Security Scanning)

```yaml
security_scanning:
  dependencies:
    tool: Snyk / Dependabot
    frequency: daily
    severity_threshold: medium
    
  code_security:
    tool: Semgrep / SonarQube
    rules:
      - sql_injection
      - xss_vulnerability
      - hardcoded_secret
      
  secrets_detection:
    tool: GitLeaks / TruffleHog
    scan_on: push, pr
    blocked_on: any_match
```

### 7.2.4 安全红线 (Security Red Lines)

```markdown
## 🔴 绝对禁止

1. **永不硬编码密钥**
   ```javascript
   // ❌ 禁止
   const apiKey = "sk-1234567890abcdef";
   
   // ✅ 正确
   const apiKey = process.env.API_KEY;
   ```

2. **永不跳过权限检查**
   ```python
   # ❌ 禁止
   def delete_user(user_id):
       db.delete(user_id)  # 无权限检查
       
   # ✅ 正确
   def delete_user(user_id, current_user):
       require_permission(current_user, 'delete_user')
       db.delete(user_id)
   ```

3. **永不相信用户输入**
   - 全部验证
   - 参数化查询
   - 输出转义

4. **永不泄露错误详情到前端**
   ```javascript
   // ❌ 禁止
   res.json({ error: e.stack });
   
   // ✅ 正确
   res.json({ error: 'Internal server error' });
   ```
```

---

## 7.3 存储规范

```
docs/coding-agent-context/
├── 07-security-context/
│   ├── README.md                    # 本文档 (索引)
│   ├── auth/
│   │   ├── authentication.md         # 认证机制
│   │   ├── authorization.md           # 授权模型
│   │   └── session-management.md      # 会话管理
│   ├── data-protection/
│   │   ├── sensitive-data-types.md   # 敏感数据类型
│   │   └── encryption-standards.md   # 加密标准
│   ├── scanning/
│   │   ├── dependency-scanning.md    # 依赖扫描
│   │   └── code-security.md          # 代码安全
│   └── incidents/
│       └── security-response.md      # 安全响应流程
```

---

## 7.4 合规要求

| 标准 | 要求 | 适用范围 |
|------|------|----------|
| GDPR | 数据删除权、数据 portability | EU 用户数据 |
| SOC 2 | 安全、可用、处理完整性 | 所有服务 |
| PCI-DSS | 支付卡数据保护 | 支付处理 |

---

## 7.5 与其他上下文的关系

```
安全上下文
    │
    ├──→ 约束: 项目规则 (安全是强制规范)
    │
    ├──→ 依赖: 环境上下文 (环境配置影响安全)
    │
    ├──→ 验证: 质量保障 (安全测试是质量门禁)
    │
    └──→ 影响: 工具上下文 (工具使用受限)
```

---

*文档版本: 1.0.0*  
*创建时间: 2026-04-29*  
*负责维度: 安全上下文*
