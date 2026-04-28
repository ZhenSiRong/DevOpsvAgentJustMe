#!/usr/bin/env python3
"""
Fetch MCP Server — 纯 Python 标准库实现（urllib）

支持工具：
- http_get: 发送 HTTP GET 请求
- http_post: 发送 HTTP POST 请求（JSON/form 数据）

运行方式:
    python3 fetch_server.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.parse
import ssl
from typing import Any


# 不验证 SSL 证书（内网/测试环境常用）
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

TOOLS = [
    {
        "name": "http_get",
        "description": "发送 HTTP GET 请求并返回响应内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "请求 URL"},
                "headers": {"type": "object", "description": "额外请求头"},
                "timeout": {"type": "integer", "description": "超时秒数（默认30）"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "http_post",
        "description": "发送 HTTP POST 请求（支持 JSON 和 form 数据）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "请求 URL"},
                "data": {"type": "object", "description": "POST 数据对象（自动转 JSON）"},
                "form": {"type": "object", "description": "form 数据（与 data 二选一）"},
                "headers": {"type": "object", "description": "额外请求头"},
                "timeout": {"type": "integer", "description": "超时秒数（默认30）"},
            },
            "required": ["url"],
        },
    },
]


def _http_get(args: dict) -> dict:
    url = args["url"]
    headers = args.get("headers", {})
    timeout = args.get("timeout", 30)

    req = urllib.request.Request(url, method="GET")
    for k, v in headers.items():
        req.add_header(k, str(v))

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            result = {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": body[:5000],  # 限制返回大小
            }
            text = json.dumps(result, ensure_ascii=False, indent=2)
            return {"content": [{"type": "text", "text": text}], "isError": False}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        result = {"status": e.code, "reason": e.reason, "body": body[:2000]}
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"请求失败: {e}"}], "isError": True}


def _http_post(args: dict) -> dict:
    url = args["url"]
    data = args.get("data")
    form = args.get("form")
    headers = args.get("headers", {})
    timeout = args.get("timeout", 30)

    if form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        req_headers = {"Content-Type": "application/x-www-form-urlencoded", **headers}
    elif data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        req_headers = {"Content-Type": "application/json", **headers}
    else:
        body = b""
        req_headers = headers

    req = urllib.request.Request(url, data=body, method="POST")
    for k, v in req_headers.items():
        req.add_header(k, str(v))

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
            result = {
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": resp_body[:5000],
            }
            text = json.dumps(result, ensure_ascii=False, indent=2)
            return {"content": [{"type": "text", "text": text}], "isError": False}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        result = {"status": e.code, "reason": e.reason, "body": body[:2000]}
        text = json.dumps(result, ensure_ascii=False, indent=2)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"请求失败: {e}"}], "isError": True}


TOOL_HANDLERS = {
    "http_get": _http_get,
    "http_post": _http_post,
}


# ============================================================
#  MCP 协议框架（与 filesystem_server.py 相同，自包含）
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
        name="fetch-mcp-server",
        version="1.0.0",
        tools=TOOLS,
    )
    server.run()
