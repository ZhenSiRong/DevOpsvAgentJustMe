import asyncio, sys, re
sys.path.insert(0, '/root/devops-agent/src')
from devops_agent.cli.client import DevOpsClient
from rich.console import Console
from rich.markdown import Markdown

console = Console()

async def test():
    client = DevOpsClient()
    result = await client.create_session('test')
    sid = result.get('data', {}).get('session_id')
    
    content = ''
    async for event, payload in client.stream_chat('hi', sid):
        if event == 'output':
            content = payload.get('reply', '')
        elif event == 'done':
            break
    
    pattern = r'<think>([\s\S]*?)<\/think>'
    match = re.search(pattern, content)
    if match:
        think = match.group(1).strip()
        main = re.sub(pattern, '', content).strip()
        console.print(f'[dim]think len={len(think)}, main len={len(main)}[/dim]')
    else:
        think = None
        main = content
        console.print('[red]THINK NOT FOUND[/red]')
    
    console.print(f'[dim]main starts with: {repr(main[:80])}[/dim]')
    
    console.print('\n[bold bright_blue]Agent:[/bold bright_blue]')
    if think:
        console.print(f'[dim]💭 思考过程: {think[:100]}...[/dim]')
    console.print(Markdown(main))
    
    await client.delete_session(sid)
    await client.close()

asyncio.run(test())
