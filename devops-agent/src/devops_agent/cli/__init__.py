"""DevOps Agent CLI / TUI 模块

终端客户端，模拟前端调用后端 API 接口。

使用:
    python -m devops_agent.cli
    python -m devops_agent.cli --url http://192.168.187.129:8000
"""

from .app import DevOpsTUI
from .client import DevOpsClient
from .main import main

__all__ = ["DevOpsTUI", "DevOpsClient", "main"]
