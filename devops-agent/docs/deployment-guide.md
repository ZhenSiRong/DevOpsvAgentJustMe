# DevOps Agent 部署与使用指南

> 面向国产化环境（龙芯 loongarch64 + 麒麟高级服务器版V11）的运维智能体平台部署说明。
> 本文档覆盖从零到生产环境可访问的完整部署流程。

---

## 目录

1. [概述](#1-概述)
2. [系统要求](#2-系统要求)
3. [环境准备](#3-环境准备)
4. [后端部署](#4-后端部署)
5. [前端构建与部署](#5-前端构建与部署)
6. [启动与验证](#6-启动与验证)
7. [systemd 服务化（推荐）](#7-systemd-服务化推荐)
8. [环境配置详解](#8-环境配置详解)
9. [故障排查](#9-故障排查)
10. [维护与升级](#10-维护与升级)
11. [附录](#11-附录)

---

## 1. 概述

DevOps Agent 采用 B/S 架构：

- **后端**：FastAPI + Uvicorn（Python 3.12+），提供 REST API 与 SSE 流式响应
- **前端**：React 18 + Vite 构建的 SPA，生产环境下由后端直接挂载为静态资源
- **数据库**：SQLite（单文件，零外部依赖）
- **安全层**：以 `devops-runner` 受限用户执行系统命令，配合白名单 + 正则校验

部署完成后，访问 `http://<服务器IP>:8000/` 即可使用 Web 界面。

---

## 2. 系统要求

### 2.1 硬件与操作系统

| 项目 | 要求 |
|------|------|
| CPU 架构 | x86_64（当前开发/测试）或 loongarch64（最终目标机） |
| 操作系统 | 麒麟高级服务器版 V11（Swan25）或兼容的 Linux 发行版 |
| 内存 | ≥ 2GB（推荐 4GB，LLM 推理不发生在本地） |
| 磁盘 | ≥ 5GB 可用空间 |
| 网络 | 可访问 LLM API 服务商（DeepSeek / MiniMax / 通义千问等） |

### 2.2 软件依赖

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.12+ | 必须使用 3.12，部分类型语法依赖 `py312` 特性 |
| pip | ≥ 23.0 | 与 Python 3.12 配套 |
| Node.js | 18+ | 仅前端构建时需要 |
| npm | 9+ | 或 yarn / pnpm |
| dnf | — | 麒麟V11 系统包管理器 |
| gcc / make | — | 编译 Python 或某些 Python 包时需要 |
| sqlite3 | ≥ 3.35 | 系统自带即可 |

---

## 3. 环境准备

以下操作在**目标服务器**（VM 或物理机）上以 `root` 用户执行。

### 3.1 安装系统基础包

```bash
# 更新系统
dnf update -y

# 安装构建工具与依赖
dnf install -y gcc gcc-c++ make libffi-devel openssl-devel \
    bzip2-devel zlib-devel readline-devel sqlite-devel \
    wget curl tar git

# 安装 sudo（如未安装）
dnf install -y sudo
```

### 3.2 安装 Python 3.12

麒麟 V11 默认可能只提供 Python 3.9/3.11，需要从源码编译 3.12：

```bash
# 方式一：使用项目提供的编译脚本
cd /opt
git clone <你的仓库地址> devops-agent  # 或 SCP 上传后解压
cd devops-agent
bash build_python312.sh

# 验证
python3 --version   # 应显示 Python 3.12.9
pip3 --version
```

> **注意**：`build_python312.sh` 会将 Python 安装到 `/usr/local/python312/`，并创建符号链接 `python3 → python3.12`。若系统已有 `python3` 命令，原命令会被备份为 `python3.11.bak`。

若脚本执行失败，可手动按以下步骤编译：

```bash
cd /tmp
curl -L -o python312.tgz https://www.python.org/ftp/python/3.12.9/Python-3.12.9.tgz
tar xzf python312.tgz
cd Python-3.12.9
./configure --prefix=/usr/local/python312 --enable-shared --with-lto \
    LDFLAGS='-Wl,-rpath,/usr/local/python312/lib'
make -j$(nproc)
make altinstall
ln -sf /usr/local/python312/bin/python3.12 /usr/bin/python3
ln -sf /usr/local/python312/bin/pip3.12 /usr/bin/pip3
```

### 3.3 安装 Node.js（前端构建用）

如服务器也需要执行前端构建：

```bash
# 方式一：使用 NodeSource 仓库
curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
dnf install -y nodejs

# 验证
node --version   # v20.x
npm --version
```

> **建议**：前端构建也可在 Windows 开发机上完成，仅将构建产物 `dist/` 上传到服务器。此时服务器**不需要**安装 Node.js。

---

## 4. 后端部署

### 4.1 上传项目代码

**方式一：Git 克隆（推荐，有版本管理）**

```bash
cd /opt
git clone <仓库地址> devops-agent
cd devops-agent
```

**方式二：SCP 从 Windows 开发机上传**

在 Windows `cmd` 中执行（**不要用 PowerShell**，会吞 stderr）：

```cmd
cd /d A:\DevOpsAgentPlaning
scp -r devops-agent root@192.168.187.128:/opt/
```

> IP 地址以实际 VM 分配为准。若 VM 使用 NAT + DHCP，IP 可能变化，请在 VM 内执行 `ip addr` 确认。

### 4.2 创建 Python 虚拟环境

```bash
cd /opt/devops-agent
python3 -m venv venv
source venv/bin/activate

# 确认在虚拟环境中
which python3   # 应显示 /opt/devops-agent/venv/bin/python3
```

### 4.3 安装 Python 依赖

**生产环境**（仅运行所需）：

```bash
pip install --upgrade pip
pip install -e .
```

**开发环境**（包含测试与代码检查工具）：

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

> 首次安装可能需要编译少量依赖（如 `cryptography`），请确保系统已安装 `gcc` 和 `openssl-devel`。

### 4.4 配置环境变量

```bash
cp .env.example .env
vim .env
```

**必填项**（不填服务无法启动或无法调用 LLM）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `LLM_API_KEY` | LLM 服务商 API Key | `sk-xxxxxxxx` |
| `LLM_BASE_URL` | 服务商 API 地址 | `https://api.minimaxi.com/v1` |
| `LLM_MODEL` | 模型名称 | `MiniMax-M2.1` |

**强烈建议修改**（安全相关）：

| 变量 | 说明 | 建议值 |
|------|------|--------|
| `JWT_SECRET_KEY` | JWT 签名密钥 | 随机生成 ≥32 字符的字符串 |
| `SAFE_EXEC_USER` | 受限执行用户 | `devops-runner`（需先创建该用户） |

其余配置项保持默认值即可运行，详见 [第 8 节](#8-环境配置详解)。

### 4.5 创建安全执行用户（关键步骤）

Agent 执行系统命令时，默认以 `devops-runner` 用户运行（最小权限原则）。必须创建该用户并配置 sudo：

```bash
# 创建受限用户（无登录权限）
useradd -r -s /sbin/nologin -M devops-runner

# 配置 sudo 白名单
visudo -f /etc/sudoers.d/devops-agent
```

在打开的编辑器中写入以下内容：

```
# DevOps Agent 执行白名单
devops-runner ALL=(root) NOPASSWD: /usr/bin/logrotate *
devops-runner ALL=(root) NOPASSWD: /usr/bin/systemctl status *
devops-runner ALL=(root) NOPASSWD: /usr/bin/systemctl restart *
devops-runner ALL=(root) NOPASSWD: /usr/bin/journalctl *
devops-runner ALL=(root) NOPASSWD: /usr/bin/df *
devops-runner ALL=(root) NOPASSWD: /usr/bin/du *
devops-runner ALL=(root) NOPASSWD: /usr/bin/ps *
devops-runner ALL=(root) NOPASSWD: /usr/bin/netstat *
devops-runner ALL=(root) NOPASSWD: /usr/bin/ss *
devops-runner ALL=(root) NOPASSWD: /usr/bin/cat *
devops-runner ALL=(root) NOPASSWD: /usr/bin/ls *
devops-runner ALL=(root) NOPASSWD: /usr/bin/find *
devops-runner ALL=(root) NOPASSWD: /usr/bin/grep *
devops-runner ALL=(root) NOPASSWD: /usr/bin/head *
devops-runner ALL=(root) NOPASSWD: /usr/bin/tail *
devops-runner ALL=(root) NOPASSWD: /usr/bin/wc *
devops-runner ALL=(root) NOPASSWD: /usr/bin/sort *
devops-runner ALL=(root) NOPASSWD: /usr/bin/uniq *
devops-runner ALL=(root) NOPASSWD: /usr/bin/cut *
devops-runner ALL=(root) NOPASSWD: /usr/bin/awk *
devops-runner ALL=(root) NOPASSWD: /usr/bin/sed *
```

> **注意**：`.env` 中的 `SUDO_WHITELIST` 是应用层白名单，`/etc/sudoers.d/` 是 OS 层白名单。两者必须同时配置，命令才能实际执行。

验证 sudo 配置语法：

```bash
visudo -c   # 应显示 "parsed OK"
```

### 4.6 初始化数据库

数据库为 SQLite 单文件，首次启动时会**自动建表**。也可手动初始化：

```bash
cd /opt/devops-agent
source venv/bin/activate
python -m scripts.init_db
```

预期输出：

```
✅ 数据库初始化完成，表已创建于: /opt/devops-agent/data/devops_agent.db
```

数据库文件默认位于项目根目录的 `data/devops_agent.db`，可通过 `DATABASE_URL` 修改路径。

---

## 5. 前端构建与部署

### 5.1 开发环境构建（Windows 或 Linux）

```bash
cd devops-agent/frontend

# 安装依赖
npm install

# 生产构建
npm run build
```

构建产物输出到 `frontend/dist/` 目录。

### 5.2 上传构建产物到服务器

**若在前端目录下执行构建**：

```bash
# 确认 dist 目录存在
ls -la devops-agent/frontend/dist/
```

**若在 Windows 上构建后上传**：

```cmd
cd /d A:\DevOpsAgentPlaning\devops-agent\frontend
scp -r dist root@192.168.187.128:/opt/devops-agent/frontend/
```

### 5.3 后端自动挂载

FastAPI 应用在启动时会**自动检测** `frontend/dist/` 目录是否存在，若存在则挂载为根路径静态资源：

```python
# main.py 中的逻辑
static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
```

这意味着前端无需单独部署 Web 服务器，访问 `http://<IP>:8000/` 即可加载前端页面，API 请求走 `http://<IP>:8000/api/v1/...`。

> 若 `frontend/dist/` 不存在，后端仍然可以独立运行，只是没有 Web 界面，需通过 `curl` 或 TUI 客户端访问 API。

---

## 6. 启动与验证

### 6.1 启动服务

**开发模式**（带热重载，仅开发使用）：

```bash
cd /opt/devops-agent
source venv/bin/activate
uvicorn devops_agent.main:app --reload --host 0.0.0.0 --port 8000
```

**生产模式**（无热重载，多 worker）：

```bash
cd /opt/devops-agent
source venv/bin/activate
uvicorn devops_agent.main:app --host 0.0.0.0 --port 8000 --workers 2
```

启动成功后应看到日志：

```
🚀 DevOps Agent 启动中...
✅ 动态工具加载完成: 10 个
✅ DevOps Agent 启动完成 (0.35s)
前端静态文件已挂载: /opt/devops-agent/frontend/dist
```

### 6.2 验证步骤

**步骤 1：健康检查**

```bash
curl http://192.168.187.128:8000/health
```

预期响应：

```json
{
  "status": "ok",
  "app": "DevOps-Agent",
  "version": "0.1.0",
  "db_connected": true,
  "uptime_seconds": 12.34
}
```

**步骤 2：应用信息**

```bash
curl http://192.168.187.128:8000/api/v1/info
```

**步骤 3：探针测试**

```bash
curl http://192.168.187.128:8000/api/v1/probe/disk
```

预期返回磁盘使用情况 JSON。

**步骤 4：对话测试（SSE 流式）**

```bash
curl -N -X POST http://192.168.187.128:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "查看系统磁盘使用情况", "session_id": "test-001"}'
```

应看到 SSE 事件流输出，包含推理链路和最终响应。

**步骤 5：Web 界面**

在浏览器打开 `http://192.168.187.128:8000/`，应能看到登录/聊天界面。

---

## 7. systemd 服务化（推荐）

生产环境建议使用 systemd 管理后端进程，确保崩溃后自动重启。

### 7.1 创建服务文件

```bash
vim /etc/systemd/system/devops-agent.service
```

写入以下内容（根据实际路径调整）：

```ini
[Unit]
Description=DevOps Agent 运维智能体
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/devops-agent
Environment="PATH=/opt/devops-agent/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"
Environment="PYTHONPATH=/opt/devops-agent/src"
ExecStart=/opt/devops-agent/venv/bin/uvicorn devops_agent.main:app --host 0.0.0.0 --port 8000 --workers 2
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 7.2 启动并启用服务

```bash
# 重载 systemd
systemctl daemon-reload

# 启动服务
systemctl start devops-agent

# 设置开机自启
systemctl enable devops-agent

# 查看状态
systemctl status devops-agent

# 查看日志
journalctl -u devops-agent -f
```

### 7.3 常用操作

| 操作 | 命令 |
|------|------|
| 启动 | `systemctl start devops-agent` |
| 停止 | `systemctl stop devops-agent` |
| 重启 | `systemctl restart devops-agent` |
| 查看日志 | `journalctl -u devops-agent -n 100 --no-pager` |
| 实时跟踪日志 | `journalctl -u devops-agent -f` |

---

## 8. 环境配置详解

### 8.1 配置分层机制

DevOps Agent 采用**分层配置**设计：

1. **.env 文件**：提供默认值，应用启动时读取一次，适合固定基础设施配置（如数据库路径、监听端口）
2. **数据库 configs 表**：提供运行时覆盖值，可通过 `/api/v1/config` 接口热修改，适合频繁变动的配置（如 LLM 模型、API Key）
3. **合并规则**：Agent 每次对话请求开始时，调用 `get_llm_runtime_config()` 合并两层配置，DB 值优先级高于 .env 值

### 8.2 配置项完整清单

| 变量名 | 默认值 | 必填 | 说明 |
|--------|--------|------|------|
| **应用配置** |
| `APP_NAME` | `DevOps-Agent` | 否 | 应用名称，显示在 Swagger 文档和 info 接口 |
| `APP_DEBUG` | `false` | 否 | 调试模式。`true` 时开启热重载，异常返回堆栈 |
| `APP_HOST` | `0.0.0.0` | 否 | 监听地址。`0.0.0.0` 表示所有网卡 |
| `APP_PORT` | `8000` | 否 | 监听端口 |
| **LLM 配置（OpenAI 协议）** |
| `LLM_PROTOCOL` | `openai` | 否 | 协议类型：`openai` 或 `anthropic` |
| `LLM_BASE_URL` | `https://api.minimaxi.com/v1` | **是** | LLM API 基础地址 |
| `LLM_API_KEY` | — | **是** | API Key |
| `LLM_MODEL` | `MiniMax-M2.1` | **是** | 模型标识符 |
| `LLM_TEMPERATURE` | `0.3` | 否 | 采样温度，0~2 |
| `LLM_MAX_TOKENS` | `4096` | 否 | 最大生成 token 数 |
| **LLM 配置（Anthropic 协议备用）** |
| `ANTHROPIC_BASE_URL` | `https://api.minimaxi.com/anthropic` | 否 | Anthropic 兼容端点地址 |
| `ANTHROPIC_API_KEY` | — | 否 | Anthropic 协议 API Key |
| `ANTHROPIC_MODEL` | `MiniMax-M2.1` | 否 | Anthropic 协议模型名 |
| **数据库** |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/devops_agent.db` | 否 | SQLite 文件路径。`./` 表示项目根目录 |
| **安全层** |
| `SAFE_EXEC_USER` | `devops-runner` | 否 | 命令执行的受限 OS 用户 |
| `EXEC_TIMEOUT` | `30` | 否 | 单条命令执行超时（秒） |
| `SUDO_WHITELIST` | 见 .env.example | 否 | sudo 白名单命令列表，逗号分隔 |
| **认证** |
| `JWT_SECRET_KEY` | `change-this-secret-key` | 否 | JWT 签名密钥，生产环境必须修改 |
| `JWT_ALGORITHM` | `HS256` | 否 | JWT 算法 |
| `JWT_EXPIRE_MINUTES` | `1440` | 否 | Token 过期时间（分钟），默认 24 小时 |
| **探针** |
| `PROBE_TIMEOUT` | `10` | 否 | 单次探针命令超时（秒） |
| `PROBE_MAX_ROUNDS` | `5` | 否 | Agent 感知循环最大轮次 |

### 8.3 运行时热切换 LLM 模型

无需重启服务，通过 API 即可切换模型：

```bash
# 查看当前运行时配置
curl http://192.168.187.128:8000/api/v1/config

# 修改模型（立即生效）
curl -X PUT http://192.168.187.128:8000/api/v1/config \
  -H "Content-Type: application/json" \
  -d '{
    "llm.model": "deepseek-chat",
    "llm.base_url": "https://api.deepseek.com/v1",
    "llm.api_key": "sk-your-new-key"
  }'
```

> 运行时配置存储在 SQLite `configs` 表中，重启后仍然保留。如需恢复 .env 默认值，可调用 `DELETE /api/v1/config/{key}` 删除对应键。

---

## 9. 故障排查

### 9.1 启动失败

| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| `ModuleNotFoundError: No module named 'fastapi'` | 未在虚拟环境中安装依赖 | 执行 `source venv/bin/activate && pip install -e .` |
| `Permission denied` | 非 root 用户监听 80 端口，或文件权限不足 | 改用 ≥1024 端口，或检查目录权限 |
| `Address already in use` | 8000 端口被占用 | `lsof -i :8000` 查找并终止占用进程，或修改 `APP_PORT` |
| `frontend/dist` 目录不存在 | 前端未构建或未上传 | 执行前端构建并确认 `dist/` 存在 |

### 9.2 数据库错误

| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| `unable to open database file` | `data/` 目录无写权限 | `chmod 755 data/` 或检查磁盘空间 |
| 表缺失错误 | 数据库文件已存在但表未创建 | 手动执行 `python -m scripts.init_db` |
| `database is locked` | 并发写入冲突 | SQLite WAL 模式已启用，通常无需处理。若频繁出现，考虑减少 worker 数量 |

### 9.3 LLM 调用失败

| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| `401 Unauthorized` | API Key 错误 | 检查 `.env` 或运行时配置中的 `LLM_API_KEY` |
| `404 Not Found` | 模型名称错误或 base_url 错误 | 核对服务商文档，确认模型标识符和端点地址 |
| `Connection timeout` | 服务器无法访问 LLM API | 检查网络连通性：`curl -I <LLM_BASE_URL>` |
| 流式响应中断 | SSE 连接被代理/防火墙中断 | 确认中间层（如 Nginx）未缓存 SSE 响应 |

### 9.4 命令执行失败

| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| `安全校验拦截` | 命令命中危险模式 | 检查命令内容，确认不在保护路径上 |
| `白名单拒绝` | 命令不在 EXECUTION_WHITELIST 中 | 修改 `.env` 的 `SUDO_WHITELIST` 并重启，或调整代码中的 `EXECUTION_WHITELIST` |
| `权限不足: 无法以用户 'devops-runner' 执行` | sudo 未配置或配置错误 | 检查 `/etc/sudoers.d/devops-agent` 是否存在且语法正确，执行 `visudo -c` |
| `命令执行超时` | 命令执行超过 30 秒 | 修改 `.env` 中 `EXEC_TIMEOUT`，或优化命令 |

### 9.5 前端白屏/404

| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| 访问 `/` 返回 404 | `frontend/dist` 不存在或路径错误 | 检查后端日志中的 "前端静态文件目录不存在" 警告，确认 dist 路径 |
| 页面加载但 API 报错 | 前端代理配置错误 | 生产环境前端直接访问同域 API，无需代理。若分开部署，修改前端环境变量指向正确后端地址 |
| CORS 错误 | 前后端域名不一致 | `main.py` 中 CORS 已设置为 `allow_origins=["*"]`（MVP 阶段），生产环境应限制为具体域名 |

---

## 10. 维护与升级

### 10.1 日志管理

- **应用日志**：由 Uvicorn / Python logging 输出到 stdout/stderr，systemd 模式下通过 `journalctl` 查看
- **数据库**：SQLite 文件位于 `data/devops_agent.db`，建议定期备份
- **审计日志**：所有 Agent 操作记录在 `audit_logs` 表中，可通过 `/api/v1/audit` 接口查询

### 10.2 备份

```bash
# 备份数据库
cp /opt/devops-agent/data/devops_agent.db /backup/devops_agent_$(date +%Y%m%d).db

# 备份 .env 配置
cp /opt/devops-agent/.env /backup/devops-agent.env
```

### 10.3 更新代码

```bash
cd /opt/devops-agent

# 拉取最新代码
git pull origin master

# 若依赖有变化，重新安装
source venv/bin/activate
pip install -e .

# 数据库迁移自动执行（lifespan 钩子），无需手动操作

# 重启服务
systemctl restart devops-agent
```

### 10.4 数据库迁移说明

本项目使用 SQLite，无传统 ORM 迁移工具。 schema 变更策略：

1. **新增表/索引**：在 `connection.py` 的 `CREATE_TABLES_SQL` 中追加 `CREATE TABLE IF NOT EXISTS`，启动时自动执行
2. **新增列**：在 `DatabaseManager._migrate_audit_logs()` 中参考已有模式，以 `ALTER TABLE ... ADD COLUMN` 方式自动补全
3. **破坏性变更**：需手动导出数据 → 删除库文件 → 重启自动建表 → 导入数据

---

## 11. 附录

### 附录 A：SELinux 配置（可选，Phase 2 安全增强）

若目标机开启 SELinux enforcing 模式，需加载自定义 policy module 以允许 `devops-runner` 执行受限命令。详见 [SELinux 策略设计文档](selinux-policy-design.md)。

简要步骤：

```bash
# 检查 SELinux 状态
getenforce   # 若为 Enforcing，继续以下步骤

# 编译并加载策略模块
checkmodule -M -m -o devops-agent.mod devops-agent.te
semodule_package -o devops-agent.pp -m devops-agent.mod
semodule -i devops-agent.pp
```

> **注意**：当前 SELinux policy 处于设计完成待部署状态，MVP 阶段可先以 `setenforce 0` 测试，但正式环境必须完成 policy 部署。

### 附录 B：loongarch64 迁移注意事项

当前在 x86_64 VMware 虚拟机开发，最终需迁移到龙芯 loongarch64 真机：

| 风险点 | 应对措施 |
|--------|----------|
| `uvloop` / `grpcio` 无预编译 whl | 使用 `pip install --no-binary :all:` 强制源码编译，或替换为纯 Python 实现 |
| Python 3.12 需重新编译 | 在 loongarch64 上重新执行 `build_python312.sh` |
| Node.js 前端构建 | 在 x86_64 构建后仅上传 `dist/` 产物，loongarch64 无需安装 Node.js |
| 依赖测试 | 每新增一个 Python 包，先在 loongarch64 上执行 `pip install` 验证 |

### 附录 C：API 端点速查

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/info` | GET | 应用信息与模块状态 |
| `/api/v1/chat` | POST | 普通对话（非流式） |
| `/api/v1/chat/stream` | POST | SSE 流式对话 |
| `/api/v1/sessions` | CRUD | 会话管理 |
| `/api/v1/probe/{type}` | GET | OS 探针（disk/process/network/logs） |
| `/api/v1/execute` | POST | 安全命令执行 |
| `/api/v1/audit` | GET | 审计日志查询 |
| `/api/v1/reasoning/{session_id}` | GET | 推理链路查询 |
| `/api/v1/safety/status` | GET | 安全层状态 |
| `/api/v1/tools` | GET/POST | 工具列表与动态注册 |
| `/api/v1/config` | GET/PUT/DELETE | 运行时配置管理 |

完整 API 契约见 `docs-planning/05-api-contract.md`。

### 附录 D：测试

```bash
cd /opt/devops-agent
source venv/bin/activate

# 运行全部测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_safety_validator.py -v
pytest tests/test_probe.py -v
pytest tests/test_api_chat.py -v
```

---

*文档版本：v1.0 | 最后更新：2026-04-27 | 维护团队：DevOps Agent 开发团队*
