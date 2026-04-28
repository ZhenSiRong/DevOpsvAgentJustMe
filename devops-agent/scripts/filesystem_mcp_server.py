#!/usr/bin/env python3
"""
Filesystem MCP Server — 符合 Model Context Protocol 标准的文件系统工具 Server。

提供工具：
  - read_file    读取文本文件内容
  - list_directory  列出目录下的文件和子目录
  - file_info    获取文件/目录的元数据

安全限制：所有路径必须位于 ALLOWED_ROOT 之下，禁止越界访问。

用法：
    python3 filesystem_mcp_server.py [--root /path/to/allowed]
"""

import sys
import json
import os
import stat
import time
import argparse


def _send(obj: dict):
    """发送 JSON-RPC 消息（stdio 行协议）"""
    raw = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(raw + "\n")
    sys.stdout.flush()


def _recv() -> dict | None:
    """接收一行 JSON-RPC 消息"""
    line = sys.stdin.readline()
    if not line:
        return None
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


class FilesystemMCPServer:
    def __init__(self, allowed_root: str):
        self.allowed_root = os.path.abspath(allowed_root)
        self.initialized = False

    # ------------------------------------------------------------------
    # 安全校验
    # ------------------------------------------------------------------
    def _sanitize_path(self, rel_path: str) -> str:
        """将用户输入的相对路径解析为绝对路径，并校验不越界。"""
        # 去掉开头的 /
        rel_path = rel_path.lstrip("/")
        target = os.path.abspath(os.path.join(self.allowed_root, rel_path))
        # 严格校验：target 必须是 allowed_root 的子路径
        if not target.startswith(self.allowed_root + os.sep) and target != self.allowed_root:
            raise ValueError(f"路径越界: {rel_path}")
        return target

    # ------------------------------------------------------------------
    # 工具实现
    # ------------------------------------------------------------------
    def tool_read_file(self, arguments: dict) -> dict:
        rel_path = arguments.get("path", "")
        target = self._sanitize_path(rel_path)
        if not os.path.isfile(target):
            return {"content": [{"type": "text", "text": f"错误: 不是文件或不存在 — {rel_path}"}]}
        try:
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()
            return {"content": [{"type": "text", "text": content}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"读取失败: {e}"}]}

    def tool_list_directory(self, arguments: dict) -> dict:
        rel_path = arguments.get("path", "")
        target = self._sanitize_path(rel_path)
        if not os.path.isdir(target):
            return {"content": [{"type": "text", "text": f"错误: 不是目录或不存在 — {rel_path}"}]}
        try:
            entries = []
            for name in sorted(os.listdir(target)):
                full = os.path.join(target, name)
                st = os.stat(full)
                entries.append({
                    "name": name,
                    "type": "directory" if stat.S_ISDIR(st.st_mode) else "file",
                    "size": st.st_size,
                    "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                })
            text = json.dumps(entries, ensure_ascii=False, indent=2)
            return {"content": [{"type": "text", "text": text}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"列出目录失败: {e}"}]}

    def tool_file_info(self, arguments: dict) -> dict:
        rel_path = arguments.get("path", "")
        target = self._sanitize_path(rel_path)
        if not os.path.exists(target):
            return {"content": [{"type": "text", "text": f"错误: 路径不存在 — {rel_path}"}]}
        try:
            st = os.stat(target)
            info = {
                "path": rel_path,
                "absolute": target,
                "type": "directory" if stat.S_ISDIR(st.st_mode) else "file",
                "size": st.st_size,
                "permissions": stat.filemode(st.st_mode),
                "owner_uid": st.st_uid,
                "owner_gid": st.st_gid,
                "atime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_atime)),
                "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
                "ctime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_ctime)),
            }
            text = json.dumps(info, ensure_ascii=False, indent=2)
            return {"content": [{"type": "text", "text": text}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"获取信息失败: {e}"}]}

    # ------------------------------------------------------------------
    # 工具 Schema
    # ------------------------------------------------------------------
    TOOLS = [
        {
            "name": "read_file",
            "description": "读取指定路径的文本文件内容。路径为相对于允许根目录的相对路径。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件相对路径，例如 'README.md' 或 'src/main.py'",
                    }
                },
                "required": ["path"],
            },
        },
        {
            "name": "list_directory",
            "description": "列出指定目录下的所有文件和子目录。路径为相对于允许根目录的相对路径。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录相对路径，例如 '.' 或 'src'",
                    }
                },
                "required": ["path"],
            },
        },
        {
            "name": "file_info",
            "description": "获取文件或目录的详细元数据（大小、权限、修改时间等）。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件或目录的相对路径",
                    }
                },
                "required": ["path"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # 消息处理
    # ------------------------------------------------------------------
    def handle(self, msg: dict):
        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            self.initialized = True
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {
                        "name": "filesystem-mcp-server",
                        "version": "1.0.0",
                    },
                },
            })

        elif method == "notifications/initialized":
            pass  # 无需响应

        elif method == "tools/list":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.TOOLS},
            })

        elif method == "tools/call":
            params = msg.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            handler = getattr(self, f"tool_{tool_name}", None)
            if handler:
                try:
                    result = handler(arguments)
                except Exception as e:
                    result = {"content": [{"type": "text", "text": f"执行错误: {e}"}]}
            else:
                result = {
                    "content": [{"type": "text", "text": f"未知工具: {tool_name}"}],
                    "isError": True,
                }

            _send({"jsonrpc": "2.0", "id": msg_id, "result": result})

        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {}})

        else:
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })

    def run(self):
        while True:
            msg = _recv()
            if msg is None:
                break
            self.handle(msg)


def main():
    parser = argparse.ArgumentParser(description="Filesystem MCP Server")
    parser.add_argument("--root", default="/root/devops-agent", help="允许访问的根目录")
    args = parser.parse_args()

    server = FilesystemMCPServer(args.root)
    server.run()


if __name__ == "__main__":
    main()
