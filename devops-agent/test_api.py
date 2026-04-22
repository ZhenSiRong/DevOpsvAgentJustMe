import urllib.request, json

# Test sessions POST
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/sessions",
    data=json.dumps({"title": "测试会话"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    resp = urllib.request.urlopen(req)
    print("SESSIONS POST:", resp.read().decode())
except Exception as e:
    print("SESSIONS POST ERROR:", e)

# Test chat
req2 = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/chat",
    data=json.dumps({"message": "查看磁盘使用"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    resp2 = urllib.request.urlopen(req2)
    print("CHAT:", resp2.read().decode())
except Exception as e:
    print("CHAT ERROR:", e)
