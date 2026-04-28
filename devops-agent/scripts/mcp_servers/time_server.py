#!/usr/bin/env python3
"""
Time MCP Server — 纯 Python 标准库实现

支持工具：
- get_current_time: 获取当前时间（多种格式）
- format_timestamp: 将 Unix 时间戳格式化为可读字符串
- calculate_duration: 计算两个时间之间的差值
- sleep_seconds: 让进程休眠指定秒数（用于定时任务测试）

运行方式:
    python3 time_server.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone, timedelta

TOOLS = [
    {
        "name": "get_current_time",
        "description": "获取当前系统时间，支持多种输出格式和时区",
        "inputSchema": {
            "type": "object",
            "properties": {
                "format": {"type": "string", "description": "输出格式: iso/rfc/epoch/local（默认iso）"},
                "timezone": {"type": "string", "description": "时区偏移，如 +08:00（默认系统时区）"},
            },
            "required": [],
        },
    },
    {
        "name": "format_timestamp",
        "description": "将 Unix 时间戳（秒）转换为可读日期字符串",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timestamp": {"type": "integer", "description": "Unix 时间戳（秒）"},
                "format": {"type": "string", "description": "输出格式: iso/rfc/local（默认iso）"},
            },
            "required": ["timestamp"],
        },
    },
    {
        "name": "calculate_duration",
        "description": "计算两个 ISO 时间字符串之间的差值",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "起始时间 ISO 格式"},
                "end": {"type": "string", "description": "结束时间 ISO 格式（默认当前时间）"},
            },
            "required": ["start"],
        },
    },
    {
        "name": "sleep_seconds",
        "description": "让进程休眠指定秒数（用于定时任务/轮询测试）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "description": "休眠秒数（最大60）"},
            },
            "required": ["seconds"],
        },
    },
]


def _parse_timezone(tz_str: str | None) -> timezone | None:
    if not tz_str:
        return None
    try:
        # 支持 +08:00 或 -05:00 格式
        sign = 1 if tz_str[0] == "+" else -1
        parts = tz_str[1:].split(":")
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
        return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
    except Exception:
        return None


def _get_current_time(args: dict) -> dict:
    fmt = args.get("format", "iso")
    tz_str = args.get("timezone")
    tz = _parse_timezone(tz_str)

    now = datetime.now(tz) if tz else datetime.now()

    if fmt == "epoch":
        text = str(int(now.timestamp()))
    elif fmt == "rfc":
        text = now.strftime("%a, %d %b %Y %H:%M:%S %z")
    elif fmt == "local":
        text = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    else:
        text = now.isoformat()

    return {"content": [{"type": "text", "text": text}], "isError": False}


def _format_timestamp(args: dict) -> dict:
    ts = args["timestamp"]
    fmt = args.get("format", "iso")

    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if fmt == "rfc":
            text = dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        elif fmt == "local":
            text = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S %Z")
        else:
            text = dt.isoformat()
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"格式化失败: {e}"}], "isError": True}


def _calculate_duration(args: dict) -> dict:
    start_str = args["start"]
    end_str = args.get("end")

    try:
        start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00")) if end_str else datetime.now(timezone.utc)
        delta = end - start

        result = {
            "total_seconds": delta.total_seconds(),
            "days": delta.days,
            "hours": delta.seconds // 3600,
            "minutes": (delta.seconds % 3600) // 60,
            "seconds": delta.seconds % 60,
            "is_negative": delta.total_seconds() < 0,
        }
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"计算失败: {e}"}], "isError": True}


def _sleep_seconds(args: dict) -> dict:
    seconds = args.get("seconds", 0)
    if seconds < 0 or seconds > 60:
        return {"content": [{"type": "text", "text": "休眠秒数必须在 0~60 之间"}], "isError": True}
    time.sleep(seconds)
    return {"content": [{"type": "text", "text": f"休眠完成: {seconds}s"}], "isError": False}


TOOL_HANDLERS = {
    "get_current_time": _get_current_time,
    "format_timestamp": _format_timestamp,
    "calculate_duration": _calculate_duration,
    "sleep_seconds": _sleep_seconds,
}


# ============================================================
#  MCP 协议框架（自包含）
# ============================================================

class MCPServerBase:
    def __init__(self, name: str, version: str, tools: list):
        self.name = name
        self.version = version
        self.tools = tools
        self._initialized = False

    def run(self):
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                self._handle_message(line)
            except KeyboardInterrupt:
                break
            except Exception as e:
                self._send_error(None, -32603, f"Internal error: {e}")

    def _handle_message(self, line: str):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            self._send_error(None, -32700, "Parse error")
            return

        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        if msg_id is None:
            if method == "notifications/initialized":
                pass
            return

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "tools/list":
                result = self._handle_tools_list(params)
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            elif method == "ping":
                result = {}
            else:
                self._send_error(msg_id, -32601, f"Method not found: {method}")
                return
            self._send_response(msg_id, result)
        except Exception as e:
            self._send_error(msg_id, -32603, f"Internal error: {e}")

    def _handle_initialize(self, params: dict) -> dict:
        self._initialized = True
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": self.name, "version": self.version},
        }

    def _handle_tools_list(self, params: dict) -> dict:
        return {"tools": self.tools}

    def _handle_tools_call(self, params: dict) -> dict:
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return {"content": [{"type": "text", "text": f"未知工具: {name}"}], "isError": True}
        return handler(arguments)

    def _send_response(self, msg_id, result):
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _send_error(self, msg_id, code, message):
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    server = MCPServerBase(
        name="time-mcp-server",
        version="1.0.0",
        tools=TOOLS,
    )
    server.run()
