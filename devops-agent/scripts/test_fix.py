import urllib.request, json

def test(cmd):
    req = urllib.request.Request(
        'http://localhost:8000/api/v1/execute',
        data=json.dumps({'command': cmd, 'timeout': 30}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as r:
        d = json.loads(r.read().decode())
    data = d.get('data', {})
    st = data.get('status')
    ec = data.get('exit_code')
    print(cmd + ' -> status=' + str(st) + ' exit_code=' + str(ec))
    if data.get('stderr'):
        print('  stderr: ' + data.get('stderr')[:80])
    if data.get('stdout'):
        print('  stdout: ' + data.get('stdout')[:60])

test('ls')
test('top -b -n1')
test('df -h')
test('free -m')
test('ps aux')
