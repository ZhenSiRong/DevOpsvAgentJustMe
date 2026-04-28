import urllib.request, json

# Test GET whitelist
req = urllib.request.Request('http://localhost:8000/api/v1/safety/whitelist')
with urllib.request.urlopen(req) as r:
    d = json.loads(r.read().decode())
print('GET whitelist: code=' + str(d.get('code')) + ' count=' + str(d.get('data',{}).get('count')))

# Test unrestricted execute (terminal path)
req = urllib.request.Request(
    'http://localhost:8000/api/v1/execute',
    data=json.dumps({'command': 'whoami', 'timeout': 30}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req) as r:
    d = json.loads(r.read().decode())
data = d.get('data', {})
print('execute whoami: status=' + str(data.get('status')) + ' stdout=' + str(data.get('stdout','')).strip())

# Test agent execute (should still check whitelist)
req = urllib.request.Request(
    'http://localhost:8000/api/v1/safety/execute',
    data=json.dumps({'command': 'whoami', 'timeout': 30}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
with urllib.request.urlopen(req) as r:
    d = json.loads(r.read().decode())
data = d.get('data', {})
print('safetyExecute whoami: status=' + str(data.get('status')))
