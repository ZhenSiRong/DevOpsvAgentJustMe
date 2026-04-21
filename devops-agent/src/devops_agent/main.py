"""FastAPI 应用入口 - 启动点 + 生命周期事件钩子"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
    #  注册路由模块（Day 4 完成 — 7 个路由端点）
    # ============================================================
    from .api.routes import health, probe, execute, chat, sessions, audit

    app.include_router(health.router)          # /health, /api/v1/info
    app.include_router(probe.router)            # /api/v1/probe/*
    app.include_router(execute.router)          # /api/v1/execute
    app.include_router(chat.router)             # /api/v1/chat
    app.include_router(sessions.router)         # /api/v1/sessions/*
    app.include_router(audit.router)            # /api/v1/audit/*

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "app": settings.app_name}

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
