# 08 - 工具上下文 (Tool Context)

> **父文档**: [Coding Agent 上下文体系](../Coding-Agent-Context-Taxonomy.md)  
> **定义**: Agent 可用的工具能力及其使用约束

---

## 8.1 文档目的

工具上下文让 Agent 清楚自己 "能做什么" 和 "不能做什么"，以及每种工具的正确使用方法。

---

## 8.2 组成部分

### 8.2.1 文件系统工具 (File System Tools)

| 工具 | 用途 | 权限 |
|------|------|------|
| read_file | 读取文件内容 | 工作目录内 |
| write_to_file | 创建/覆盖文件 | 工作目录内 |
| replace_in_file | 精确替换文本 | 工作目录内 |
| delete_file | 删除文件 | 需要确认 |
| search_content | 内容搜索 | 工作目录内 |
| search_file | 文件名搜索 | 工作目录内 |
| list_dir | 目录列表 | 工作目录内 |

#### 使用示例

```bash
# ✅ 正确用法
read_file(path="src/utils/helper.ts")
replace_in_file(
  filePath="src/utils/helper.ts",
  old_str="const VERSION = '1.0';",
  new_str="const VERSION = '2.0';"
)

# ⚠️ 需要注意
# - old_str 必须完全匹配，包括缩进和换行
# - 不要替换过大的代码块
```

### 8.2.2 代码分析与生成工具

```markdown
## 代码分析工具

### 语义搜索
- 用途: 查找函数定义、调用关系
- 工具: search_content (正则表达式)

### 结构分析
- 用途: 理解模块依赖
- 方法: 读取 import/require 语句

### 代码生成
- 用途: 生成样板代码、测试
- 约束: 必须符合项目规范
```

### 8.2.3 执行命令工具 (Execute Command)

```bash
execute_command(command="npm run build", requires_approval=false)
execute_command(command="rm -rf node_modules", requires_approval=true)
```

#### 危险命令黑名单

| 命令 | 原因 | 替代方案 |
|------|------|----------|
| `rm -rf /` | 删根目录 | `rm -rf ./target` |
| `rm -rf node_modules` | 删除依赖 | `npm ci` |
| `git push --force` | 覆盖历史 | `git push` |
| `DROP TABLE` | 删除数据 | `DELETE FROM` |

### 8.2.4 外部服务集成 (External Services)

| 服务 | 工具 | 用途 |
|------|------|------|
| 数据库 | 数据库客户端/CLI | 数据查询和修改 |
| 云服务 | AWS/GCP/Azure CLI | 资源管理 |
| API | HTTP 客户端 | 第三方集成 |
| 部署 | Docker/K8s CLI | 容器编排 |

### 8.2.5 特殊能力 (Special Capabilities)

```markdown
## 特殊工具

### 多模态理解
- 图像: 读取图片文件，理解图表
- 文档: 解析 PDF、Word、Excel
- 视频: 理解视频内容

### 文档生成
- Markdown: 技术文档
- API 文档: OpenAPI/Swagger
- 测试报告: 测试覆盖率

### 图表绘制
- Mermaid: 流程图、序列图
- PlantUML: UML 图
- 架构图: C4 模型
```

---

## 8.3 工具使用约束

### 8.3.1 权限限制

```markdown
## 权限边界

### 可访问区域
- 项目源代码目录
- 文档目录
- 配置文件

### 限制区域
- 系统关键目录 (/etc, /usr)
- 其他用户目录
- 密钥文件 (*.key, *.pem)

### 禁止操作
- 修改 git 历史
- 绕过代码审查
- 直接操作生产环境
```

### 8.3.2 操作审批流程

```yaml
operations:
  auto_approve:
    - 文件读写
    - 代码搜索
    - 单元测试
    
  require_confirmation:
    - 删除文件
    - git commit
    - 安装依赖
    
  require_approval:
    - 删除目录
    - 修改配置
    - 运行迁移
```

### 8.3.3 审计日志

```markdown
## 操作记录

所有操作都会被记录:
- 操作类型
- 目标文件/资源
- 执行时间
- 操作结果

审计日志用途:
1. 问题追溯
2. 安全审计
3. 性能分析
```

---

## 8.4 存储规范

```
docs/coding-agent-context/
├── 08-tool-context/
│   ├── README.md                    # 本文档 (索引)
│   ├── file-system/
│   │   ├── file-tools.md             # 文件操作工具
│   │   └── search-tools.md           # 搜索工具
│   ├── code-tools/
│   │   ├── analysis-tools.md         # 分析工具
│   │   └── generation-tools.md       # 生成工具
│   ├── execution/
│   │   ├── command-execution.md      # 命令执行
│   │   └── dangerous-commands.md      # 危险命令
│   └── integrations/
│       ├── external-services.md      # 外部服务
│       └── special-capabilities.md   # 特殊能力
```

---

## 8.5 与其他上下文的关系

```
工具上下文
    │
    ├──→ 约束: 环境上下文 (工具依赖环境)
    │
    ├──→ 限制: 安全上下文 (安全限制工具使用)
    │
    ├──→ 服务: 对话上下文 (对话触发工具调用)
    │
    └──→ 验证: 质量保障 (工具操作需要验证)
```

---

*文档版本: 1.0.0*  
*创建时间: 2026-04-29*  
*负责维度: 工具上下文*
