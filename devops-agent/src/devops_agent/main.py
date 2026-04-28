"""FastAPI 应用入口 - 启动点 + 生命周期事件钩子"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
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

    # CORS：允许前端跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # MVP 全开放，生产环境应限制
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 全局异常处理器
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("未处理异常: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc) if settings.app_debug else "服务器内部错误",
                }
            },
        )

    # ============================================================
    #  注册路由模块（Day 4 完成 — 8 个路由端点 + Day 5 动态工具）
    # ============================================================
    from .api.routes import health, probe, execute, chat, sessions, audit, reasoning, safety, tools, config, mcp

    app.include_router(health.router)          # /health, /api/v1/info
    app.include_router(probe.router)            # /api/v1/probe/*
    app.include_router(execute.router)          # /api/v1/execute
    app.include_router(chat.router)             # /api/v1/chat
    app.include_router(sessions.router)         # /api/v1/sessions/*
    app.include_router(audit.router)            # /api/v1/audit/*
    app.include_router(reasoning.router)        # /api/v1/reasoning/*
    app.include_router(safety.router)           # /api/v1/safety/*
    app.include_router(tools.router)            # /api/v1/tools/* (动态工具)
    app.include_router(config.router)           # /api/v1/config/* (系统配置)
    app.include_router(mcp.router)              # /api/v1/mcp/* (MCP Server 管理)

    # 挂载前端静态文件（如果存在）
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    static_dir = os.path.abspath(static_dir)
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
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
