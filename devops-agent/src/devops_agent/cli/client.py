"""TUI API 客户端 —— 封装后端所有接口调用

基于 httpx 的异步 HTTP 客户端，对应前端 api/client.js 的所有功能。
支持 SSE 流式响应解析。
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

API_BASE = "/api/v1"


class DevOpsClient:
    """DevOps Agent 后端 API 客户端"""

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)

    async def health(self) -> dict[str, Any]:
        """健康检查"""
        r = await self.client.get(f"{self.base_url}/health")
        r.raise_for_status()
        return r.json()

    # ============================================================
    #  会话管理
    # ============================================================

    async def list_sessions(self, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        r = await self.client.get(
            f"{self.base_url}{API_BASE}/sessions",
            params={"page": page, "page_size": page_size},
        )
        r.raise_for_status()
        return r.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        r = await self.client.get(f"{self.base_url}{API_BASE}/sessions/{session_id}")
        r.raise_for_status()
        return r.json()

    async def create_session(self, title: str = "新对话") -> dict[str, Any]:
        r = await self.client.post(
            f"{self.base_url}{API_BASE}/sessions",
            json={"title": title},
        )
        r.raise_for_status()
        return r.json()

    async def delete_session(self, session_id: str) -> dict[str, Any]:
        r = await self.client.delete(f"{self.base_url}{API_BASE}/sessions/{session_id}")
        r.raise_for_status()
        return r.json()

    # ============================================================
    #  对话
    # ============================================================

    async def send_chat(self, message: str, session_id: str | None = None) -> dict[str, Any]:
        r = await self.client.post(
            f"{self.base_url}{API_BASE}/chat",
            json={"message": message, "session_id": session_id},
        )
        r.raise_for_status()
        return r.json()

    async def stream_chat(
        self,
        message: str,
        session_id: str | None = None,
    ) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        """SSE 流式对话，yield (event_name, payload)"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}{API_BASE}/chat/stream",
                json={"message": message, "session_id": session_id},
                headers={"Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()

                buffer = ""
                current_event: str | None = None
                current_data: str | None = None

                async for chunk in response.aiter_text():
                    buffer += chunk
                    lines = buffer.split("\n")
                    buffer = lines.pop() if lines else ""

                    for line in lines:
                        line = line.strip()
                        if line.startswith("event:"):
                            current_event = line[6:].strip()
                        elif line.startswith("data:"):
                            current_data = line[5:].strip()
                        elif line == "" and current_event and current_data:
                            try:
                                payload = json.loads(current_data)
                            except json.JSONDecodeError:
                                payload = {"raw": current_data}
                            yield current_event, payload
                            current_event = None
                            current_data = None

                # flush remaining buffer
                if buffer.strip():
                    for line in buffer.strip().split("\n"):
                        line = line.strip()
                        if line.startswith("event:"):
                            current_event = line[6:].strip()
                        elif line.startswith("data:"):
                            current_data = line[5:].strip()
                if current_event and current_data:
                    try:
                        payload = json.loads(current_data)
                    except json.JSONDecodeError:
                        payload = {"raw": current_data}
                    yield current_event, payload

    async def get_chat_history(
        self, session_id: str, page: int = 1, page_size: int = 50
    ) -> dict[str, Any]:
        r = await self.client.get(
            f"{self.base_url}{API_BASE}/chat/history",
            params={"session_id": session_id, "page": page, "page_size": page_size},
        )
        r.raise_for_status()
        return r.json()

    # ============================================================
    #  OS 探针
    # ============================================================

    async def probe_disk(self, path: str = "/var/log") -> dict[str, Any]:
        r = await self.client.get(
            f"{self.base_url}{API_BASE}/probe/disk",
            params={"path": path},
        )
        r.raise_for_status()
        return r.json()

    async def probe_processes(self, **params) -> dict[str, Any]:
        r = await self.client.get(
            f"{self.base_url}{API_BASE}/probe/processes", params=params
        )
        r.raise_for_status()
        return r.json()

    async def probe_network(self, action: str = "connections", hostname: str | None = None) -> dict[str, Any]:
        params = {"action": action}
        if hostname:
            params["hostname"] = hostname
        r = await self.client.get(f"{self.base_url}{API_BASE}/probe/network", params=params)
        r.raise_for_status()
        return r.json()

    async def probe_logs(self, **params) -> dict[str, Any]:
        r = await self.client.get(f"{self.base_url}{API_BASE}/probe/logs", params=params)
        r.raise_for_status()
        return r.json()

    # ============================================================
    #  命令执行
    # ============================================================

    async def execute_command(
        self, command: str, timeout: int = 30, dry_run: bool = False, session_id: str | None = None
    ) -> dict[str, Any]:
        r = await self.client.post(
            f"{self.base_url}{API_BASE}/execute",
            json={"command": command, "timeout": timeout, "dry_run": dry_run, "session_id": session_id},
        )
        r.raise_for_status()
        return r.json()

    # ============================================================
    #  安全层
    # ============================================================

    async def safety_status(self) -> dict[str, Any]:
        r = await self.client.get(f"{self.base_url}{API_BASE}/safety/status")
        r.raise_for_status()
        return r.json()

    async def validate_command(self, command: str, context: dict | None = None) -> dict[str, Any]:
        r = await self.client.post(
            f"{self.base_url}{API_BASE}/safety/validate",
            json={"command": command, "context": context},
        )
        r.raise_for_status()
        return r.json()

    # ============================================================
    #  系统配置（LLM 动态切换）
    # ============================================================

    async def get_llm_config(self) -> dict[str, Any]:
        r = await self.client.get(f"{self.base_url}{API_BASE}/config/llm")
        r.raise_for_status()
        return r.json()

    async def update_config(self, configs: list[dict[str, str]]) -> dict[str, Any]:
        r = await self.client.put(
            f"{self.base_url}{API_BASE}/config",
            json={"configs": configs},
        )
        r.raise_for_status()
        return r.json()

    async def reset_config(self, key: str) -> None:
        r = await self.client.delete(f"{self.base_url}{API_BASE}/config/{key}")
        if r.status_code != 204:
            r.raise_for_status()

    async def reset_all_config(self) -> dict[str, Any]:
        r = await self.client.post(f"{self.base_url}{API_BASE}/config/reset-all")
        r.raise_for_status()
        return r.json()

    async def detect_llm_config(
        self,
        base_url: str,
        api_key: str,
        model: str,
        apply: bool = True,
    ) -> dict[str, Any]:
        r = await self.client.post(
            f"{self.base_url}{API_BASE}/config/detect",
            json={"base_url": base_url, "api_key": api_key, "model": model, "apply": apply},
        )
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        await self.client.aclose()
