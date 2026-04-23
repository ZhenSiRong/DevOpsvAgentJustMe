import sys
sys.path.insert(0, '/root/devops-agent/src')
from devops_agent.cli.app import DevOpsTUI

tui = DevOpsTUI()

# 模拟带 think 块的 assistant 消息
tui.messages = [
    type('Msg', (), {'role': 'user', 'content': 'hi'})(),
    type('Msg', (), {'role': 'assistant', 'content': '<think>用户只是打了个招呼</think>\n\n你好！我是运维助手。'})(),
]

print("=== BEFORE FIX (模拟旧逻辑) ===")
for msg in tui.messages[-3:]:
    role = "你" if msg.role == "user" else "Agent"
    content = msg.content[:60].replace("\n", " ")
    print(f"  {role}: {content}...")

print("\n=== AFTER FIX (新逻辑) ===")
for msg in tui.messages[-3:]:
    role = "你" if msg.role == "user" else "Agent"
    if msg.role == "assistant":
        main, _ = tui.parse_think_block(msg.content)
        content = main[:60].replace("\n", " ") if main else ""
    else:
        content = msg.content[:60].replace("\n", " ")
    print(f"  {role}: {content}...")
