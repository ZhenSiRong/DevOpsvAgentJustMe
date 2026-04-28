#!/usr/bin/env python3
"""最小化 MCP Server —— 端到端测试用

提供两个简单工具：
- echo: 回显输入文本
- add: 两数相加

用法::

    python3 test_mcp_server.py

然后通过 stdio 进行 JSON-RPC 通信。
"""

import json
import sys


def send(msg: dict) -> None:
    """发送 JSON-RPC 消息到 stdout（行分隔）。"""
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_initialize(msg_id):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test-server", "version": "1.0.0"},
        },
    }


def handle_tools_list(msg_id):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "tools": [
                {
                    "name": "echo",
                    "description": "回显输入文本",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "要回显的文本",
                            }
                        },
                        "required": ["text"],
                    },
                },
                {
                    "name": "add",
                    "description": "两数相加",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "a": {
                                "type": "number",
                                "description": "第一个数",
                            },
                            "b": {
                                "type": "number",
                                "description": "第二个数",
                            },
                        },
                        "required": ["a", "b"],
                    },
                },
            ]
        },
    }


def handle_tools_call(msg_id, params):
    name = params.get("name", "")
    args = params.get("arguments", {})

    if name == "echo":
        text = args.get("text", "")
        result = {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        }
    elif name == "add":
        total = args.get("a", 0) + args.get("b", 0)
        result = {
            "content": [{"type": "text", "text": str(total)}],
            "isError": False,
        }
    else:
        result = {
            "content": [{"type": "text", "text": f"未知工具: {name}"}],
            "isError": True,
        }

    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def handle_ping(msg_id):
    return {"jsonrpc": "2.0", "id": msg_id, "result": {}}


def main():
    while True:
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            break
        if not line:
            break

        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            send({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            })
            continue

        msg_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        # 通知类消息（无 id）不需要响应
        if msg_id is None:
            continue

        if method == "initialize":
            send(handle_initialize(msg_id))
        elif method == "tools/list":
            send(handle_tools_list(msg_id))
        elif method == "tools/call":
            send(handle_tools_call(msg_id, params))
        elif method == "ping":
            send(handle_ping(msg_id))
        else:
            send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            })


if __name__ == "__main__":
    main()
