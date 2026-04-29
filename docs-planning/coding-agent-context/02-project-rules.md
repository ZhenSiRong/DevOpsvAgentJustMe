# 02 - 项目规则 (Project Rules)

> **父文档**: [Coding Agent 上下文体系](../Coding-Agent-Context-Taxonomy.md)  
> **定义**: 约束代码编写的标准和规范体系

---

## 2.1 文档目的

项目规则确保团队成员和 AI Agent 在代码编写时保持一致性，是代码质量的基础保障。

---

## 2.2 组成部分

### 2.2.1 代码规范 (Coding Standards)

#### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 变量 | camelCase | `userName`, `totalCount` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| 函数 | camelCase, 动词前缀 | `getUserById()`, `fetchData()` |
| 类名 | PascalCase | `UserService`, `OrderController` |
| 文件名 | kebab-case | `user-service.js`, `order_controller.py` |
| 组件名 | PascalCase | `UserCard.vue`, `LoginForm.tsx` |

#### 代码风格

```markdown
## 通用规则

1. 缩进: 4空格 (或配置 .editorconfig)
2. 行宽: 最大 120 字符
3. 换行: 运算符在行尾
4. 空行: 函数间留1空行, 类成员分组留空行
5. 注释: 
   - 公共 API 必须有 JSDoc/文档字符串
   - 复杂逻辑需要行内解释
   - 禁止无用注释
```

#### 提交规范

```
{类型}({范围}): {简短描述}

[可选正文]

[可选脚注]
```

**类型列表**:
| 类型 | 说明 |
|------|------|
| feat | 新功能 |
| fix | 修复 bug |
| docs | 文档变更 |
| style | 格式调整 |
| refactor | 重构 |
| test | 测试相关 |
| chore | 构建/工具 |

### 2.2.2 架构规则 (Architecture Rules)

```markdown
## 模块划分原则

1. 单一职责: 每个模块只负责一件事
2. 高内聚低耦合: 模块内部紧密相关, 模块间最小依赖
3. 依赖方向: 外层依赖内层, 内层不关心外层

## 分层架构

presentation/    ← 用户界面层
    ↓
application/     ← 用例/服务编排层
    ↓
domain/          ← 业务实体和规则 (核心)
    ↓
infrastructure/  ← 外部依赖 (数据库, API)
```

### 2.2.3 测试规则 (Testing Rules)

| 规则 | 要求 |
|------|------|
| 覆盖率 | 核心逻辑 ≥ 80% |
| 必须覆盖 | 边界条件、异常路径 |
| 禁止 | 禁止 mock 内部实现 |
| 命名 | `describe`/`it` 使用自然语言 |

```javascript
// ✅ 正确示例
describe('UserService', () => {
  describe('createUser', () => {
    it('should throw ValidationError when email is invalid', () => {
      // ...
    });
  });
});
```

### 2.2.4 安全规则 (Security Rules)

```markdown
## 安全红线

1. 禁止硬编码密钥/凭证
2. 禁止 SQL 拼接, 必须参数化查询
3. 禁止用户输入直接渲染 (XSS 防护)
4. 敏感数据必须加密存储
5. 权限校验不许跳过
```

---

## 2.3 存储规范

```
docs/coding-agent-context/
├── 02-project-rules/
│   ├── README.md                    # 本文档 (索引)
│   ├── coding-standards/
│   │   ├── naming-conventions.md
│   │   ├── code-style.md
│   │   └── commit-convention.md
│   ├── architecture/
│   │   └── module-rules.md
│   ├── testing/
│   │   └── test-standards.md
│   └── security/
│       └── security-red-lines.md
```

---

## 2.4 配置文件映射

| 规范 | 配置文件 |
|------|----------|
| 代码风格 | `.editorconfig`, `.prettierrc`, `.eslintrc` |
| 提交规范 | `.github/commit-convention.md` |
| 测试规范 | `jest.config.js`, `pytest.ini` |
| 安全扫描 | `.snyk`, `sonar-project.properties` |

---

## 2.5 强制级别

| 级别 | 标识 | 说明 | 示例 |
|------|------|------|------|
| 必须 | 🔴 MUST | 违反会导致 CI 失败 | 参数校验、权限检查 |
| 应该 | 🟡 SHOULD | 强烈建议, 有合理原因可例外 | 命名规范、注释要求 |
| 可以 | 🟢 MAY | 最佳实践, 酌情使用 | 日志级别、代码分组 |

---

## 2.6 与其他上下文的关系

```
项目规则
    │
    ├──→ 约束: 技术上下文 (基于技术选型)
    │
    ├──→ 来源: 项目记忆 (基于历史经验)
    │
    ├──→ 影响: 质量保障 (定义检查标准)
    │
    └──→ 依赖: 安全上下文 (安全是底线)
```

---

*文档版本: 1.0.0*  
*创建时间: 2026-04-29*  
*负责维度: 项目规则*
