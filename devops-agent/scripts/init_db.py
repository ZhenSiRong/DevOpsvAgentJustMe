"""手动初始化数据库（也可通过 FastAPI lifespan 自动执行）"""
import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from devops_agent.db.connection import db_manager


async def main():
    await db_manager.init_tables()
    print("✅ 数据库初始化完成，表已创建于:", db_manager.DATABASE_PATH)
    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
