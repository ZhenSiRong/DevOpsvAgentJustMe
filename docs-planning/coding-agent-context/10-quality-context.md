# 10 - 质量保障上下文 (Quality Context)

> **父文档**: [Coding Agent 上下文体系](../Coding-Agent-Context-Taxonomy.md)  
> **定义**: 代码质量标准、测试要求和评审流程

---

## 10.1 文档目的

质量保障上下文确保交付的代码符合项目标准，功能经过充分测试，并且经过了必要的评审。

---

## 10.2 组成部分

### 10.2.1 代码质量标准 (Code Quality Standards)

#### 质量指标

| 指标 | 阈值 | 说明 |
|------|------|------|
| 测试覆盖率 | ≥ 80% | 核心逻辑 100% |
| 代码重复率 | < 5% | DRY 原则 |
|圈复杂度 | ≤ 15 | 函数复杂度 |
| 行长度 | ≤ 120 | 可读性 |
| 注释覆盖率 | 关键逻辑必须 | 不强制全部注释 |

#### 静态分析规则

```yaml
linting:
  tools:
    frontend:
      - ESLint (rules: react-hooks, import)
      - Prettier (format)
      - TypeScript strict mode
      
    backend:
      - Ruff (Python linter)
      - MyPy (type checking)
      - Black (format)
      
  severity_levels:
    error: block_merge
    warning: warn_in_pr
    info: suggest_in_pr
```

### 10.2.2 测试规范 (Testing Standards)

#### 测试金字塔

```
         ┌─────────┐
         │   E2E   │     少量冒烟测试
         │  Tests  │
         ├─────────┤
         │Integration│   API 和模块集成
         │  Tests   │
         ├─────────┤
         │  Unit    │   大量单元测试
         │  Tests   │
         └─────────┘
```

#### 测试要求

```markdown
## 必须测试的场景

1. Happy Path
   - 正常业务流程
   
2. Edge Cases
   - 空输入、null/undefined
   - 边界值 (0, -1, 最大值)
   - 特殊字符
   
3. Error Handling
   - 网络错误
   - 超时
   - 服务不可用
   
4. Security
   - SQL 注入
   - XSS
   - 未授权访问
```

#### 测试模板

```javascript
// Unit Test Template
describe('ModuleName', () => {
  describe('functionName', () => {
    it('should [expected behavior] when [condition]', () => {
      // Given
      const input = setupInput();
      
      // When
      const result = functionName(input);
      
      // Then
      expect(result).toEqual(expectedOutput);
    });
    
    it('should throw [error] when [condition]', () => {
      // ...
    });
  });
});
```

### 10.2.3 评审流程 (Review Process)

#### Pull Request 检查清单

```markdown
## PR 质量检查

### 代码审查
- [ ] 代码符合项目规范
- [ ] 没有硬编码的值
- [ ] 错误处理完整
- [ ] 日志记录适当
- [ ] 单元测试覆盖

### 安全审查
- [ ] 没有引入安全漏洞
- [ ] 敏感信息处理正确
- [ ] 权限检查完整

### 文档审查
- [ ] API 变更已更新文档
- [ ] 新增公共函数有 JSDoc
- [ ] README 如需要已更新
```

#### 评审通过标准

| 检查项 | 必须通过 |
|--------|----------|
| CI 检查 (lint, test, build) | ✅ |
| 至少 1 人 approve | ✅ |
| 无未解决的 blocking 评论 | ✅ |
| 分支是最新的 | ✅ |
| 没有直接 push 到 main | ✅ |

### 10.2.4 持续集成配置 (CI Configuration)

```yaml
ci_pipeline:
  stages:
    - lint        # 代码检查
    - test        # 测试
    - build       # 构建
    - deploy      # 部署 (staging)
    
  jobs:
    lint:
      commands:
        - npm run lint
        - npm run type-check
        
    test:
      commands:
        - npm run test:unit
        - npm run test:integration
      coverage:
        threshold: 80
        
    build:
      commands:
        - npm run build
      artifacts:
        - dist/**
        
    deploy:
      environment: staging
      only:
        - main
```

---

## 10.3 存储规范

```
docs/coding-agent-context/
├── 10-quality-context/
│   ├── README.md                    # 本文档 (索引)
│   ├── quality-standards/
│   │   ├── code-metrics.md           # 代码指标
│   │   ├── linting-rules.md          # 检查规则
│   │   └── review-checklist.md       # 评审清单
│   ├── testing/
│   │   ├── test-strategy.md          # 测试策略
│   │   ├── unit-test-standards.md   # 单元测试规范
│   │   └── e2e-test-standards.md     # E2E 测试规范
│   └── ci-cd/
│       ├── pipeline-config.md        # CI/CD 配置
│       └── quality-gates.md          # 质量门禁
```

---

## 10.4 质量门禁 (Quality Gates)

```markdown
## 门禁规则

### Commit Gate
- 代码格式检查通过
- 至少通过单元测试

### PR Gate
- 所有 CI 检查通过
- 测试覆盖率达标
- 无新的安全漏洞
- 代码审查通过

### Merge Gate
- PR 已 approved
- 分支已 rebase/main
- 无 blocking 评论
```

---

## 10.5 与其他上下文的关系

```
质量保障
    │
    ├──→ 依赖: 项目规则 (规则定义质量标准)
    │
    ├──→ 验证: 安全上下文 (安全是质量底线)
    │
    ├──→ 检查: 技术上下文 (技术债务影响质量)
    │
    └──→ 执行: 工具上下文 (使用工具进行质量检查)
```

---

*文档版本: 1.0.0*  
*创建时间: 2026-04-29*  
*负责维度: 质量保障上下文*
