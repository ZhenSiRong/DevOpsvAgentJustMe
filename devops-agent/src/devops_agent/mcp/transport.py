"""MCP 传输层 —— stdio 模式

启动外部命令作为 MCP Server，通过 stdin/stdout 进行 JSON-RPC 通信。
SSE 模式后续扩展。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from .protocol import JSONRPCRequest, JSONRPCResponse

logger = logging.getLogger(__name__)


class StdioTransport:
    """基于子进程 stdio 的 MCP 传输层。

    启动外部命令作为 MCP Server，通过 stdin/stdout 进行 JSON-RPC 通信。
    消息格式：每行一个 JSON 对象（以换行符分隔）。
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ):
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending_responses: dict[int | str, asyncio.Future] = {}
        self._req_counter = 0
        self._closed = False

    async def connect(self) -> None:
        """启动子进程，建立 stdio 连接。"""
        logger.info("启动 MCP Server: %s %s", self.command, " ".join(self.args))

        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
            cwd=self.cwd,
        )

        # 启动 stdout 读取协程
        self._reader_task = asyncio.create_task(self._read_loop())

        logger.info("MCP Server 进程已启动: pid=%s", self.process.pid)

    async def disconnect(self) -> None:
        """断开连接，终止子进程。"""
        self._closed = True

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self.process:
            if self.process.returncode is None:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self.process.kill()
                    await self.process.wait()
            logger.info("MCP Server 进程已终止")
            self.process = None

        # 取消所有 pending 请求
        for future in list(self._pending_responses.values()):
            if not future.done():
                future.set_exception(ConnectionError("MCP Server 连接已关闭"))
        self._pending_responses.clear()

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """发送 JSON-RPC 请求并等待响应。"""
        if self.process is None or self.process.stdin is None or self._closed:
            raise RuntimeError("Transport 未连接或已关闭")

        req_id = request.id
        if req_id is None:
            self._req_counter += 1
            req_id = self._req_counter
            request.id = req_id

        # 创建 Future 等待响应
        future = asyncio.get_event_loop().create_future()
        self._pending_responses[req_id] = future

        # 发送 JSON-RPC 消息（行分隔）
        line = request.to_json() + "\n"
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()

        logger.debug("-> MCP 请求: %s", line.strip()[:500])

        # 等待响应
        try:
            response = await asyncio.wait_for(future, timeout=30)
            return response
        except asyncio.TimeoutError:
            self._pending_responses.pop(req_id, None)
            raise TimeoutError(f"MCP 请求超时: {request.method}")

    async def _read_loop(self) -> None:
        """持续读取 stdout，分派响应。"""
        if self.process is None or self.process.stdout is None:
            return

        try:
            while not self._closed:
                try:
                    line = await asyncio.wait_for(
                        self.process.stdout.readline(), timeout=1
                    )
                except asyncio.TimeoutError:
                    continue

                if not line:
                    break

                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                logger.debug("<- MCP 响应: %s", line[:500])

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("收到非 JSON 行: %s", line[:200])
                    continue

                # 处理响应（带 id）
                if "id" in data:
                    req_id = data["id"]
                    future = self._pending_responses.pop(req_id, None)
                    if future and not future.done():
                        future.set_result(JSONRPCResponse.from_dict(data))

                # 处理通知（server 主动推送，无 id）
                elif "method" in data:
                    logger.debug("收到 MCP 通知: %s", data.get("method"))

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("MCP 读取循环异常: %s", e)

        finally:
            # 取消所有 pending 请求
            for future in list(self._pending_responses.values()):
                if not future.done():
                    future.set_exception(ConnectionError("MCP Server 连接已关闭"))
            self._pending_responses.clear()

    async def read_stderr(self) -> str:
        """读取 stderr 的所有输出（用于调试）。"""
        if self.process is None or self.process.stderr is None:
            return ""

        output = []
        while True:
            try:
                line = await asyncio.wait_for(
                    self.process.stderr.readline(), timeout=0.5
                )
                if not line:
                    break
                output.append(line.decode("utf-8", errors="replace"))
            except asyncio.TimeoutError:
                break

        return "".join(output)
