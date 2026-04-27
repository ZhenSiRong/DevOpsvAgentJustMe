# DevOps Agent TUI 使用教程

基于 Rich 的终端交互客户端，支持会话管理、流式对话、推理链路展示、LLM 配置热切换。

---

## 启动

```bash
# 在 VM（麒麟 V11）上执行
cd /root/devops-agent
python3 -m devops_agent.cli

# 或指定后端地址
python3 -m devops_agent.cli --url http://192.168.187.128:8000
```

启动后会先检查后端健康状态，然后加载会话列表。

---

## 界面布局

```
┌─────────────────────────────────────────────────────────────┐
│ DevOps Agent CLI                      [Health: OK]          │
├────────────────┬────────────────────────────────────────────┤
│ [Sessions]     │  User: 帮我看看磁盘空间                     │
│   Session 1    │                                            │
│   Session 2    │  Agent:                                    │
│ > Session 3    │  当前磁盘使用情况如下...                    │
│                │                                            │
│ [N]ew [D]el    │                                            │
│ [R]efresh      │                                            │
├────────────────┴────────────────────────────────────────────┤
│ > 输入消息 (Enter发送, Ctrl+C退出, /help 查看命令)          │
└─────────────────────────────────────────────────────────────┘
```

---

## 斜杠命令（/commands）

所有命令均不区分大小写，以 `/` 开头。

### 基础命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示完整命令列表 |
| `/quit` `/exit` `/q` | 退出 TUI |

### 会话管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `/new` | 创建新会话 | `/new` |
| `/delete` | 删除当前会话 | `/delete` |
| `/refresh` | 刷新会话列表 | `/refresh` |
| `/sessions` | 显示会话列表 | `/sessions` |
| `/s N` `/switch N` | 切换到第 N 个会话 | `/s 3` |

### 消息翻页

| 命令 | 说明 |
|------|------|
| `/up` | 查看更早消息（上翻页） |
| `/down` | 查看更新消息（下翻页） |

### 推理链路控制

| 命令 | 说明 |
|------|------|
| `/expand` | 展开当前消息的推理链路面板 |
| `/collapse` | 折叠推理链路面板 |
| `/verbose` | 切换详细模式（实时打印 analyze/plan/execute 过程） |
| `/think` | 切换 think 块显示（展示 LLM 内部思考过程） |

### 系统配置（LLM 热切换）

| 命令 | 说明 | 示例 |
|------|------|------|
| `/config` | 表格展示当前 LLM 配置 | `/config` |
| `/config set K V` | 修改配置项 | `/config set llm.model MiniMax-Text-01` |
| `/config reset K` | 重置单项为默认值 | `/config reset llm.temperature` |
| `/config reset-all` | 重置所有配置为默认值 | `/config reset-all` |
| `/config auto U K M` | **自动探测协议并切换** | `/config auto https://api.kimi.com/coding/v1 sk-xxx kimi-for-coding` |

---

## 快捷键

无需输入 `/`，直接按键即可。

| 按键 | 说明 |
|------|------|
| `N` | 新建会话 |
| `D` | 删除当前会话 |
| `R` | 刷新会话列表 |
| `j` / `k` | 上下移动会话选择（vim 风格） |
| `1` ~ `9` | 直接切换到对应序号的会话 |
| `Enter` | 在选中会话后按 Enter 进入该会话 |
| `Ctrl+C` | 退出程序 |

---

## 使用示例

### 场景 1：快速开始一次对话

```
> N                              # 新建会话
> 帮我查看系统磁盘使用情况      # 发送消息
Agent: 当前磁盘使用情况如下...
```

### 场景 2：切换模型后对话

```
> /config set llm.model MiniMax-Text-01
[green]已更新: llm.model[/green]

> /config
当前 LLM 配置
┌────────────┬───────────────────┬───────────────────┬──────────┐
│ 配置项     │ 当前值            │ 默认值            │ 状态     │
├────────────┼───────────────────┼───────────────────┼──────────┤
│ llm.model  │ MiniMax-Text-01   │ MiniMax-M2.1      │ 已覆盖   │
│ ...        │ ...               │ ...               │ ...      │
└────────────┴───────────────────┴───────────────────┴──────────┘

> 分析一下当前系统负载       # 使用新模型对话
```

### 场景 3：自动探测协议并切换 LLM 服务

只需提供 Base URL、API Key 和模型名，TUI 自动探测 OpenAI/Anthropic 两种协议，探测成功后自动持久化到数据库，下一条对话即时生效。

```
> /config auto https://api.kimi.com/coding/v1 sk-xxx kimi-for-coding

正在探测协议: https://api.kimi.com/coding/v1 ...

✓ 探测成功 协议: anthropic
响应预览: {"status":"ok"}...
✓ 配置已自动持久化，下一条对话即时生效

[dim]按 Enter 继续[/dim]

> 你好                          # 使用 Kimi 对话
Agent: 你好！我是 DevOps Agent...
```

**探测失败示例**：
```
> /config auto https://example.com/wrong sk-xxx model-01

✗ 探测失败
无法连接到 LLM 服务，两种协议均失败
Anthropic: 404 Not Found
OpenAI: 404 Not Found
```

**工作原理**：
1. 后端同时尝试 OpenAI (`/chat/completions`) 和 Anthropic (`/messages`) 两种协议
2. 哪个返回 200 且结构正确，自动记录该协议类型及对应字段
3. 自动写入 SQLite `configs` 表，重启后仍然保留
4. 再次执行 `/config auto` 会重新探测并覆盖之前配置
5. 使用 `/config reset-all` 可恢复为 `.env` 默认值

### 场景 4：查看推理过程

```
> /verbose                    # 开启详细模式
详细模式: 开启

> 查看最近 10 条系统日志
━━ 推理链路 ━━
👁 感知环境
🧠 分析: 用户需要查看系统日志...
📋 计划调用: journalctl_logs
⚙ 执行 journalctl_logs({'limit': 10})
✓ 结果: {'logs': [...]}
━━ 回复 ━━
Agent: 以下是最近 10 条系统日志...
```

### 场景 5：历史消息翻页

```
> /up                         # 查看更早消息
消息偏移: 10
> /up                         # 继续上翻
消息偏移: 20
> /down                       # 回到最新消息
消息偏移: 0
```

---

## 配置项说明

通过 `/config` 可查看和修改以下配置（修改后下一条对话即时生效）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `llm.protocol` | LLM 协议类型：`openai` 或 `anthropic` | `openai` |
| `llm.base_url` | OpenAI 协议 Base URL | `https://api.minimaxi.com/v1` |
| `llm.api_key` | OpenAI 协议 API Key | `.env` 中配置 |
| `llm.model` | OpenAI 协议模型名称 | `MiniMax-M2.1` |
| `llm.temperature` | 采样温度（0.0 ~ 2.0） | `0.3` |
| `llm.max_tokens` | 最大生成 token 数 | `4096` |
| `llm.anthropic_base_url` | Anthropic 协议 Base URL | `https://api.minimaxi.com/anthropic` |
| `llm.anthropic_api_key` | Anthropic 协议 API Key | `.env` 中配置 |
| `llm.anthropic_model` | Anthropic 协议模型名称 | `MiniMax-M2.1` |

**注意**：修改后的配置存储在 SQLite `configs` 表中，重启服务后仍然保留。使用 `/config reset K` 或 `/config reset-all` 可恢复为 `.env` 默认值。

---

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `后端连接失败` | 后端服务未启动 | `python3 -m uvicorn devops_agent.main:app --host 0.0.0.0 --port 8000` |
| `获取配置失败` | DB 未初始化 | 确保后端已正确启动并执行过初始化 |
| 消息发送后无响应 | 会话未创建 | 先按 `N` 新建会话，或输入 `/new` |
| 会话列表为空 | 首次使用或全部删除 | 按 `N` 创建新会话 |

---

*最后更新：2026-04-27*
