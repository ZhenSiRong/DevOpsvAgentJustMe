"""FastAPI 应用入口 - 启动点 + 生命周期事件钩子"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db.connection import db_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表，关闭时断开数据库"""
    logger.info("🚀 DevOps Agent 启动中...")
    start = time.perf_counter()

    # 初始化数据库（建表）
    await db_manager.init_tables()

    # 从数据库加载动态工具到 Registry
    from .tools import get_registry
    registry = get_registry()
    try:
        loaded = await registry.load_dynamic_tools()
        logger.info("✅ 动态工具加载完成: %d 个", loaded)
    except Exception as e:
        logger.warning("动态工具加载失败(非阻塞): %s", e)

    # 自动连接已启用的 MCP Server
    try:
        from .db.mcp_servers import list_mcp_servers
        mcp_configs = await list_mcp_servers(active_only=True)
        connected_count = 0
        for cfg in mcp_configs:
            try:
                config_dict = {
                    "id": cfg.id,
                    "name": cfg.name,
                    "transport": cfg.transport,
                    "command": cfg.command,
                    "args": cfg.args,
                    "env": cfg.env,
                    "url": cfg.url,
                    "cwd": cfg.cwd,
                }
                tool_names = await registry.connect_mcp_server(config_dict)
                connected_count += 1
                logger.info(
                    "✅ MCP Server '%s' 自动连接成功，注册 %d 个工具: %s",
                    cfg.id, len(tool_names), tool_names,
                )
            except Exception as e:
                logger.warning("MCP Server '%s' 自动连接失败: %s", cfg.id, e)
        if connected_count > 0:
            logger.info("✅ MCP Server 自动连接完成: %d/%d 个", connected_count, len(mcp_configs))
    except Exception as e:
        logger.warning("MCP Server 自动连接失败(非阻塞): %s", e)

    elapsed = time.perf_counter() - start
    logger.info("✅ DevOps Agent 启动完成 (%.2fs)", elapsed)

    yield  # 应用运行期间

    # 关闭连接
    await db_manager.close()
    logger.info("👋 DevOps Agent 已停止")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="面向国产化环境的运维智能体 — 自然语言驱动 Linux 运维",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS：按环境限制来源（* 与 credentials 不兼容，违反浏览器规范）
    _origins = [
        "http://localhost:5173",   # Vite 开发服务器
        "http://localhost:3000",   # 构建预览
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    if settings.app_debug:
        # 开发环境额外允许前端开发服务器
        pass
    # 生产环境可通过环境变量 CORS_ORIGINS 追加域名
    import os
    extra_origins = os.environ.get("CORS_ORIGINS", "")
    if extra_origins:
        _origins.extend([o.strip() for o in extra_origins.split(",") if o.strip()])

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # 速率限制中间件（Token Bucket，默认 60 req/min/IP）
    from .middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)

    # 全局异常处理器（生产环境不泄露内部细节）
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import uuid
        error_id = str(uuid.uuid4())[:8]
        logger.error("未处理异常 [%s]: %s", error_id, exc, exc_info=True)
        if settings.app_debug:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": str(exc),
                        "error_id": error_id,
                    }
                },
            )
        # 生产环境只返回错误 ID，详情在日志中查找
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误",
                    "error_id": error_id,
                }
            },
        )

    # ============================================================
    #  注册路由模块（Day 4 完成 — 8 个路由端点 + Day 5 动态工具）
    # ============================================================
    from .api.routes import health, probe, execute, chat, sessions, audit, reasoning, safety, tools, config, mcp, orchestrator, auth, prompt, knowledge, feedback
    from .auth.auth import get_current_user

    # 认证路由（无需鉴权）
    app.include_router(auth.router)              # /api/v1/auth/*

    # 可观测性（Prometheus metrics，无需鉴权）
    @app.get("/metrics")
    async def metrics():
        from fastapi.responses import PlainTextResponse
        from .metrics import render_metrics
        return PlainTextResponse(render_metrics(), media_type="text/plain; charset=utf-8")

    # 公开路由（无需鉴权）
    app.include_router(health.router)            # /health, /api/v1/info

    # 受保护路由（需 JWT 认证）
    app.include_router(probe.router,             # /api/v1/probe/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(execute.router,           # /api/v1/execute
                       dependencies=[Depends(get_current_user)])
    app.include_router(chat.router,              # /api/v1/chat
                       dependencies=[Depends(get_current_user)])
    app.include_router(sessions.router,          # /api/v1/sessions/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(audit.router,             # /api/v1/audit/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(reasoning.router,         # /api/v1/reasoning/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(safety.router,            # /api/v1/safety/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(tools.router,             # /api/v1/tools/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(config.router,            # /api/v1/config/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(mcp.router,               # /api/v1/mcp/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(orchestrator.router)      # /api/v1/orchestrator/*

    # 知识库 + Prompt 管理（需认证）
    app.include_router(prompt.router,             # /api/v1/prompt/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(knowledge.router,          # /api/v1/knowledge/*
                       dependencies=[Depends(get_current_user)])
    app.include_router(feedback.router,           # /api/v1/feedback/* /evolution/*
                       dependencies=[Depends(get_current_user)])

    # 挂载前端静态文件（如果存在）
    import os
    from fastapi.responses import FileResponse
    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    static_dir = os.path.abspath(static_dir)
    if os.path.isdir(static_dir):
        # SPA catch-all：API 路由优先匹配，未匹配的路径由这里处理
        # 如果路径对应真实静态文件则直接返回，否则回退到 index.html
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = os.path.join(static_dir, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(static_dir, "index.html"))

        logger.info("前端静态文件已挂载: %s", static_dir)
    else:
        logger.warning("前端静态文件目录不存在: %s", static_dir)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "devops_agent.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
