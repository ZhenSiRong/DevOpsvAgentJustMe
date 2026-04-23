import asyncio
import re
import sys
sys.path.insert(0, '/root/devops-agent/src')

from devops_agent.cli.client import DevOpsClient

async def test():
    client = DevOpsClient()
    result = await client.create_session("test")
    sid = result.get("data", {}).get("session_id")
    print(f"session_id={sid}")

    content = ""
    async for event, payload in client.stream_chat("hi", sid):
        if event == "output":
            content = payload.get("reply", "")
        elif event == "done":
            break

    print("=== RAW CONTENT (first 500 chars) ===")
    print(repr(content[:500]))
    print("=== END ===")

    match = re.search(r"<think>([\s\S]*?)<\/think>", content)
    if match:
        print(f"THINK FOUND: {repr(match.group(1)[:100])}")
    else:
        print("THINK NOT FOUND")
        if "<think>" in content:
            idx = content.find("<think>")
            print(f"<think> at index {idx}")
            print(f"around: {repr(content[idx:idx+200])}")

    await client.delete_session(sid)
    await client.close()

asyncio.run(test())
