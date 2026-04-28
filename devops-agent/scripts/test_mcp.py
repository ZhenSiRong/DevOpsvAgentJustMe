import urllib.request
import json

API = "http://localhost:8000"

def get(path):
    with urllib.request.urlopen(API + path) as r:
        return json.loads(r.read().decode())

def post(path, data=None):
    req = urllib.request.Request(API + path, method="POST")
    if data:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

# 1. 健康检查
print("=== 1. Health ===")
h = get("/health")
print("health:", h.get("status"), h.get("database"))

# 2. 环境检测
print("\n=== 2. Env Check ===")
e = get("/api/v1/mcp/env-check")
print("code:", e.get("code"))
for dep in e.get("data", {}).get("dependencies", []):
    v = dep.get('version') or 'N/A'
    print(f"  {dep['name']}: {'OK' if dep['available'] else 'NO'} ({v[:30]})")

# 3. JSON 导入
print("\n=== 3. JSON Import ===")
json_cfg = json.dumps({
    "mcpServers": {
        "test-filesystem": {
            "command": "python3",
            "args": ["/root/devops-agent/scripts/mcp_servers/filesystem_server.py"],
            "env": {}
        },
        "test-npm-server": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "env": {}
        }
    }
})
imp = post("/api/v1/mcp/servers/import", {"json_text": json_cfg})
print("code:", imp.get("code"))
print("success:", imp.get("data", {}).get("success_count"))
print("errors:", imp.get("data", {}).get("error_count"))
for item in imp.get("data", {}).get("imported", []):
    compat = item.get("compat", {})
    print(f"  {item['id']}: {item['action']} compat={compat.get('type')} ok={compat.get('compatible')}")

# 4. 列出配置
print("\n=== 4. List Servers ===")
srvs = get("/api/v1/mcp/servers")
print("total:", len(srvs.get("data", [])))
for s in srvs.get("data", [])[:5]:
    print(f"  {s['id']}: {s['name']} cmd={s.get('command', 'N/A')}")

# 5. 连接内置 filesystem server
print("\n=== 5. Connect builtin filesystem ===")
conn = post("/api/v1/mcp/servers/test-filesystem/connect")
print("code:", conn.get("code"))
print("tools:", conn.get("data", {}).get("tool_count"))
print("tool_names:", conn.get("data", {}).get("tool_names"))

# 6. 列出已连接
print("\n=== 6. Connected ===")
connected = get("/api/v1/mcp/connected")
print("connected servers:", len(connected.get("data", [])))

# 7. 断开
print("\n=== 7. Disconnect ===")
disc = post("/api/v1/mcp/servers/test-filesystem/disconnect")
print("code:", disc.get("code"))
print("removed:", disc.get("data", {}).get("count"))

# 8. 清理测试数据
print("\n=== 8. Cleanup ===")
for sid in ["test-filesystem", "test-npm-server"]:
    try:
        req = urllib.request.Request(API + f"/api/v1/mcp/servers/{sid}", method="DELETE")
        with urllib.request.urlopen(req) as r:
            print(f"  deleted {sid}:", json.loads(r.read().decode()).get("code"))
    except Exception as e:
        print(f"  delete {sid} error:", e)

print("\n=== All tests completed ===")
