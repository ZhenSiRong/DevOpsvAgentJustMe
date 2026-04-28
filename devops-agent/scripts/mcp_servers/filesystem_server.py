#!/usr/bin/env python3
"""
Filesystem MCP Server — 纯 Python 标准库实现

支持工具：
- read_file: 读取文件内容
- write_file: 写入文件内容（带备份）
- list_directory: 列出目录内容
- search_files: 按文件名模式搜索
- get_file_info: 获取文件元信息

运行方式:
    python3 filesystem_server.py

在 DevOps Agent 中配置:
    {
        "command": "python3",
        "args": ["/root/devops-agent/scripts/mcp_servers/filesystem_server.py"],
        "env": {}
    }
"""

from __future__ import annotations

import json
import os
import sys
import fnmatch
from datetime import datetime


# ============================================================
#  工具定义
# ============================================================

TOOLS = [
    {
        "name": "read_file",
        "description": "读取指定路径的文件内容，支持限制行数",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径"},
                "limit": {"type": "integer", "description": "最大读取行数（默认1000）"},
                "offset": {"type": "integer", "description": "起始行偏移（默认0）"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "写入或追加内容到文件（自动创建目录，写前备份）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径"},
                "content": {"type": "string", "description": "要写入的内容"},
                "append": {"type": "boolean", "description": "是否追加模式（默认false覆盖）"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "列出目录下的文件和子目录",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录绝对路径（默认当前目录）"},
            },
            "required": [],
        },
    },
    {
        "name": "search_files",
        "description": "在指定目录下递归搜索匹配文件名模式的文件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "搜索起始目录"},
                "pattern": {"type": "string", "description": "文件名匹配模式，如 *.log"},
            },
            "required": ["path", "pattern"],
        },
    },
    {
        "name": "get_file_info",
        "description": "获取文件的元信息（大小、修改时间、权限等）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录绝对路径"},
            },
            "required": ["path"],
        },
    },
]


# ============================================================
#  工具执行
# ============================================================

def _read_file(args: dict) -> dict:
    path = os.path.expanduser(args["path"])
    limit = args.get("limit", 1000)
    offset = args.get("offset", 0)

    if not os.path.exists(path):
        return {"content": [{"type": "text", "text": f"文件不存在: {path}"}], "isError": True}
    if os.path.isdir(path):
        return {"content": [{"type": "text", "text": f"路径是目录，不是文件: {path}"}], "isError": True}

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        start = max(0, offset)
        end = min(len(lines), start + limit)
        content = "".join(lines[start:end])
        return {"content": [{"type": "text", "text": content}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"读取失败: {e}"}], "isError": True}


def _write_file(args: dict) -> dict:
    path = os.path.expanduser(args["path"])
    content = args["content"]
    append = args.get("append", False)

    # 自动创建父目录
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    # 写前备份（如果文件已存在且不是追加）
    if not append and os.path.exists(path) and os.path.isfile(path):
        backup = f"{path}.bak.{int(datetime.now().timestamp())}"
        try:
            with open(path, "rb") as src:
                data = src.read()
            with open(backup, "wb") as dst:
                dst.write(data)
        except Exception:
            pass  # 备份失败不阻塞写入

    try:
        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)
        return {"content": [{"type": "text", "text": f"{'追加' if append else '写入'}成功: {path}"}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"写入失败: {e}"}], "isError": True}


def _list_directory(args: dict) -> dict:
    path = os.path.expanduser(args.get("path", "."))
    if not os.path.exists(path):
        return {"content": [{"type": "text", "text": f"目录不存在: {path}"}], "isError": True}
    if not os.path.isdir(path):
        return {"content": [{"type": "text", "text": f"路径不是目录: {path}"}], "isError": True}

    try:
        items = []
        for entry in os.listdir(path):
            full = os.path.join(path, entry)
            st = os.stat(full)
            items.append({
                "name": entry,
                "type": "directory" if os.path.isdir(full) else "file",
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
            })
        items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
        text = json.dumps(items, ensure_ascii=False, indent=2)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"列出目录失败: {e}"}], "isError": True}


def _search_files(args: dict) -> dict:
    path = os.path.expanduser(args["path"])
    pattern = args["pattern"]

    if not os.path.exists(path) or not os.path.isdir(path):
        return {"content": [{"type": "text", "text": f"目录不存在: {path}"}], "isError": True}

    try:
        matches = []
        for root, dirs, files in os.walk(path):
            for name in files:
                if fnmatch.fnmatch(name, pattern):
                    matches.append(os.path.join(root, name))
            # 限制搜索深度和数量，避免超时
            if len(matches) >= 100:
                matches.append("... (结果已截断，最多100条)")
                break
        text = "\n".join(matches) if matches else "未找到匹配文件"
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"搜索失败: {e}"}], "isError": True}


def _get_file_info(args: dict) -> dict:
    path = os.path.expanduser(args["path"])
    if not os.path.exists(path):
        return {"content": [{"type": "text", "text": f"路径不存在: {path}"}], "isError": True}

    try:
        st = os.stat(path)
        info = {
            "path": path,
            "exists": True,
            "type": "directory" if os.path.isdir(path) else "file",
            "size": st.st_size,
            "permissions": oct(st.st_mode)[-3:],
            "owner_uid": st.st_uid,
            "group_gid": st.st_gid,
            "atime": datetime.fromtimestamp(st.st_atime).isoformat(),
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
            "ctime": datetime.fromtimestamp(st.st_ctime).isoformat(),
        }
        text = json.dumps(info, ensure_ascii=False, indent=2)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"获取信息失败: {e}"}], "isError": True}


TOOL_HANDLERS = {
    "read_file": _read_file,
    "write_file": _write_file,
    "list_directory": _list_directory,
    "search_files": _search_files,
    "get_file_info": _get_file_info,
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
        name="filesystem-mcp-server",
        version="1.0.0",
        tools=TOOLS,
    )
    server.run()
