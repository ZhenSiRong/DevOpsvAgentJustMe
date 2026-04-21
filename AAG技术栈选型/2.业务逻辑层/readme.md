
## 核心框架：FastAPI + Python 3.12

**理由：**

**FastAPI** 原生支持异步（`async/await`），图中 WebSocket 端点、流式推送、多并发探针调用这些场景都能优雅处理。自动生成的 OpenAPI 文档对前后端联调也很方便。

**Pydantic v2** 做数据校验和序列化，图中那么多模块间的数据传递（tool 参数、审计日志、会话状态）都需要严格的类型约束。

---

## 各模块的具体技术栈

| 模块 | 技术选型 |
|------|---------|
| **RESTful 路由 / WebSocket** | FastAPI 原生 `APIRouter` + `WebSocket` 类，`POST /chat` 用 StreamingResponse 流式返回 |
| **认证中间件** | `fastapi-users` 或自研 JWT（`python-jose` + `passlib`），存 SQLite 用户表 |
| **MCP 运维插件** | 复用 nanoclaw-py 的 `@tool()` 装饰器 + `create_sdk_mcp_server()`，工具注册走 MCP 协议 |
| **执行引擎** | `asyncio.subprocess` 跑命令，`subprocess` 模块做进程隔离，配合 `sudo` 切换到 devops-runner 账户 |
| **命令安全校验器** | 自研 Python 模块，用正则 + 语义分析（可选 `transformers` 小模型做意图分类） |
| **内存与状态管理** | `aiosqlite` 存会话上下文，`lru_cache` 或 `cachetools` 做热数据缓存 |
| **模型层（外部 API）** | `httpx.AsyncClient` 调 LLM，`openai` 或 `anthropic` SDK 做协议兼容 |
| **上下文压缩 / 超长输出卸载** | 自研模块，`tiktoken` 算 token 数，超阈值写临时文件 |
| **模型路由 / RAG / 子代理 / 多Agent** | **MVP 阶段全部砍掉**，这些属于 Phase 3+ 的增强功能，现在不需要技术选型 |

---

## 关键依赖清单

```txt
fastapi==0.109.0          # Web 框架
uvicorn[standard]==0.27   # ASGI 服务器
websockets==12.0          # WebSocket 支持
aiosqlite==0.19.0         # 异步 SQLite
pydantic==2.6.0           # 数据校验
httpx==0.26.0             # 异步 HTTP 客户端
python-jose[cryptography] # JWT
passlib[bcrypt]           # 密码哈希
```

---

## 一个务实的建议

图里"模型路由、RAG、子代理管理、多Agent协同、Agent自定义"这五个模块，标注一下 **MVP 不实现**。它们会显著增加复杂度，但对赛题评分（功能完整性 55%）贡献有限。

先把核心链路跑通：**接收 → 探针 → LLM → 校验 → 执行 → 响应**，再考虑这些增强模块。

要不要我把业务逻辑层的目录结构（按模块划分）写出来？