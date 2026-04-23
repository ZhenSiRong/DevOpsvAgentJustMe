"""DevOps Agent CLI 入口

使用方式:
    # 默认连接 localhost:8000
    python -m devops_agent.cli

    # 指定后端地址
    python -m devops_agent.cli --url http://192.168.187.129:8000

    # 直接执行单条命令（非交互模式）
    python -m devops_agent.cli --exec "查看磁盘空间"

命令:
    /help       显示帮助
    /new        创建新会话
    /delete     删除当前会话
    /refresh    刷新会话列表
    /expand     展开推理链路详情
    /collapse   折叠推理链路
    /quit       退出

快捷键:
    N           新建会话
    D           删除当前会话
    R           刷新会话列表
    Ctrl+C      退出
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .app import DevOpsTUI
from .client import DevOpsClient

console = Console()


async def interactive_mode(base_url: str) -> int:
    """交互式 TUI 模式"""
    tui = DevOpsTUI(base_url)
    await tui.run()
    return 0


async def single_command_mode(base_url: str, message: str) -> int:
    """单命令模式（非交互）"""
    client = DevOpsClient(base_url)

    try:
        # 健康检查
        health = await client.health()
        console.print(f"[dim]后端状态: {health.get('status', 'unknown')}[/dim]\n")

        # 创建会话
        result = await client.create_session("CLI 单次对话")
        session_id = result.get("data", {}).get("session_id")

        console.print(Panel(
            Text(message, style="bold green"),
            title="用户",
            border_style="green"
        ))

        # 流式输出
        content = ""
        with console.status("[cyan]Agent 思考中...[/cyan]", spinner="dots") as status:
            async for event_name, payload in client.stream_chat(message, session_id):
                if event_name == "analyze":
                    status.update("[cyan]分析中...[/cyan]")
                elif event_name == "plan":
                    tools = payload.get("tools", [])
                    tool_names = [t.get("name", "?") for t in tools]
                    status.update(f"[cyan]计划调用: {', '.join(tool_names)}[/cyan]")
                elif event_name == "execute":
                    tool = payload.get("tool_name", "?")
                    status.update(f"[yellow]执行: {tool}...[/yellow]")
                elif event_name == "output":
                    content = payload.get("reply", "")
                elif event_name == "error":
                    content = f"[red]错误: {payload.get('error', '未知错误')}[/red]"

        from rich.markdown import Markdown
        console.print(Panel(
            Markdown(content) if content else "[dim]无回复[/dim]",
            title="Agent",
            border_style="blue"
        ))

        # 清理会话
        await client.delete_session(session_id)
        await client.close()
        return 0

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        return 1


async def probe_mode(base_url: str, probe_type: str, **kwargs) -> int:
    """探针快捷模式"""
    client = DevOpsClient(base_url)

    try:
        if probe_type == "disk":
            result = await client.probe_disk(kwargs.get("path", "/"))
        elif probe_type == "network":
            result = await client.probe_network(
                kwargs.get("action", "connections"),
                kwargs.get("hostname")
            )
        elif probe_type == "processes":
            result = await client.probe_processes()
        elif probe_type == "logs":
            result = await client.probe_logs(
                unit=kwargs.get("unit"),
                lines=kwargs.get("lines", 50)
            )
        else:
            console.print(f"[red]未知探针类型: {probe_type}[/red]")
            return 1

        from rich.json import JSON
        data = result.get("data", result)
        console.print(JSON.from_data(data))
        return 0

    except Exception as e:
        console.print(f"[red]探针执行失败: {e}[/red]")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="devops-cli",
        description="DevOps Agent 终端客户端 - 模拟前端调用后端 API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                           # 交互式 TUI 模式（默认）
  %(prog)s --url http://192.168.1.100:8000   # 指定后端地址
  %(prog)s --exec "查看磁盘空间"            # 单命令模式
  %(prog)s --probe disk --path /var        # 磁盘探针快捷调用
        """
    )

    parser.add_argument(
        "--url", "-u",
        default="http://localhost:8000",
        help="后端 API 地址 (默认: http://localhost:8000)"
    )

    parser.add_argument(
        "--exec", "-e",
        metavar="MESSAGE",
        help="执行单条命令后退出（非交互模式）"
    )

    parser.add_argument(
        "--probe", "-p",
        choices=["disk", "network", "processes", "logs"],
        help="执行探针快捷查询"
    )

    parser.add_argument(
        "--path",
        default="/",
        help="磁盘探针路径（配合 --probe disk）"
    )

    parser.add_argument(
        "--action",
        default="connections",
        help="网络探针动作（配合 --probe network）"
    )

    parser.add_argument(
        "--hostname",
        help="网络探针目标主机（配合 --probe network）"
    )

    parser.add_argument(
        "--unit",
        help="日志探针服务单元（配合 --probe logs）"
    )

    parser.add_argument(
        "--lines", "-n",
        type=int,
        default=50,
        help="日志行数（配合 --probe logs，默认 50）"
    )

    args = parser.parse_args()

    # 打印欢迎信息
    if not args.exec and not args.probe:
        console.print("""
[bold bright_blue]╔══════════════════════════════════════════════════════════════╗
║          DevOps Agent CLI - 终端客户端                        ║
║          模拟前端调用后端 API                                  ║
╚══════════════════════════════════════════════════════════════╝[/bold bright_blue]
""")
        console.print(f"[dim]后端地址: {args.url}[/dim]\n")

    # 运行模式选择
    if args.probe:
        return asyncio.run(probe_mode(args.url, args.probe,
                                     path=args.path,
                                     action=args.action,
                                     hostname=args.hostname,
                                     unit=args.unit,
                                     lines=args.lines))
    elif args.exec:
        return asyncio.run(single_command_mode(args.url, args.exec))
    else:
        return asyncio.run(interactive_mode(args.url))


if __name__ == "__main__":
    sys.exit(main())
