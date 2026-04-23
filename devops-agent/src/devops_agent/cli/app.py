"""TUI 主界面 —— 基于 Rich 的终端聊天客户端

布局：
┌─────────────────────────────────────────────────────────────┐
│ DevOps Agent CLI                      [Health: OK]          │
├────────────────┬────────────────────────────────────────────┤
│ [Sessions]     │                                            │
│   Session 1    │  User: 帮我看看磁盘空间                      │
│   Session 2    │                                            │
│ > Session 3    │  Assistant:                                 │
│                │  ┌─────────────────────────────────────┐   │
│ [N]ew [D]el    │  │ 思考过程...                          │   │
│ [R]efresh      │  └─────────────────────────────────────┘   │
│                │  当前磁盘使用情况如下...                     │
│                │                                            │
│                │                                            │
│                │                                            │
│                │                                            │
│                │                                            │
├────────────────┴────────────────────────────────────────────┤
│ > 输入消息 (Enter发送, Ctrl+C退出, /help 查看命令)           │
└─────────────────────────────────────────────────────────────┘

功能：
- 会话列表展示（创建/选择/删除/刷新）
- 流式对话（SSE 实时显示）
- 推理链路折叠面板
- Markdown 表格渲染
- 历史消息加载
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any

from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from .client import DevOpsClient

console = Console()

EVENT_COLORS = {
    "start": "dim",
    "sense": "cyan",
    "analyze": "yellow",
    "plan": "magenta",
    "execute": "orange3",
    "execute_done": "green",
    "output": "bright_blue",
    "done": "green",
    "error": "red",
}

EVENT_ICONS = {
    "start": "▶",
    "sense": "👁",
    "analyze": "🧠",
    "plan": "📋",
    "execute": "⚙",
    "execute_done": "✓",
    "output": "💬",
    "done": "✅",
    "error": "❌",
}


@dataclass
class Message:
    role: str  # user | assistant | system
    content: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)


class DevOpsTUI:
    """DevOps Agent TUI 主类"""

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self.client = DevOpsClient(base_url)
        self.sessions: list[dict[str, Any]] = []
        self.current_session_id: str | None = None
        self.messages: list[Message] = []
        self.status_text = "就绪"
        self.input_buffer = ""
        self.reasoning_collapsed = True  # 推理链路默认折叠

    async def fetch_sessions(self) -> None:
        """刷新会话列表"""
        try:
            result = await self.client.list_sessions(page=1, page_size=20)
            self.sessions = result.get("data", {}).get("items", [])
            self.status_text = f"会话数: {len(self.sessions)}"
        except Exception as e:
            self.status_text = f"[red]获取会话失败: {e}[/red]"

    async def select_session(self, session_id: str) -> None:
        """选择会话并加载历史消息"""
        self.current_session_id = session_id
        self.messages = []

        try:
            result = await self.client.get_chat_history(session_id, page_size=50)
            items = result.get("data", {}).get("items", [])
            # items 是倒序的（最新的在前），需要反转
            for item in reversed(items):
                self.messages.append(
                    Message(role=item.get("role", "user"), content=item.get("content", ""))
                )
            self.status_text = f"已加载 {len(self.messages)} 条消息"
        except Exception as e:
            self.status_text = f"[red]加载历史失败: {e}[/red]"

    async def create_session(self) -> str | None:
        """创建新会话"""
        try:
            result = await self.client.create_session("CLI 对话")
            session = result.get("data", {})
            session_id = session.get("session_id")
            await self.fetch_sessions()
            if session_id:
                await self.select_session(session_id)
            return session_id
        except Exception as e:
            self.status_text = f"[red]创建会话失败: {e}[/red]"
            return None

    async def delete_current_session(self) -> None:
        """删除当前会话"""
        if not self.current_session_id:
            self.status_text = "[yellow]请先选择一个会话[/yellow]"
            return

        try:
            await self.client.delete_session(self.current_session_id)
            self.current_session_id = None
            self.messages = []
            await self.fetch_sessions()
            self.status_text = "会话已删除"
        except Exception as e:
            self.status_text = f"[red]删除失败: {e}[/red]"

    def parse_think_block(self, content: str) -> tuple[str, str | None]:
        """提取 <think> 块"""
        import re

        pattern = r"<think>([\s\S]*?)<\/think>"
        match = re.search(pattern, content)
        if match:
            think = match.group(1).strip()
            main = re.sub(pattern, "", content).strip()
            return main, think
        return content, None

    def build_sessions_panel(self) -> Panel:
        """构建左侧会话列表面板"""
        table = Table(show_header=False, box=None, expand=True)
        table.add_column("会话", ratio=1)

        for s in self.sessions:
            sid = s.get("session_id", "")
            title = s.get("title", "未命名")
            if sid == self.current_session_id:
                table.add_row(f"[bold bright_cyan]> {title}[/bold bright_cyan]")
            else:
                table.add_row(f"  {title}")

        instructions = "\n[dim][N]新建 [D]删除 [R]刷新[/dim]"
        return Panel(
            table.render() + instructions,
            title="[bold bright_blue]会话列表[/bold bright_blue]",
            border_style="bright_blue",
            height=None,
        )

    def build_chat_panel(self) -> Panel:
        """构建右侧聊天面板"""
        content = []

        for msg in self.messages:
            if msg.role == "user":
                content.append(f"[bold bright_green]你:[/bold bright_green] {msg.content}\n")
            elif msg.role == "assistant":
                # 处理 think 块
                main, think = self.parse_think_block(msg.content)

                # 如果有推理链路事件，显示折叠面板
                if msg.events:
                    event_lines = []
                    for ev in msg.events:
                        ev_name = ev.get("event", "unknown")
                        color = EVENT_COLORS.get(ev_name, "white")
                        icon = EVENT_ICONS.get(ev_name, "•")
                        event_lines.append(f"[{color}]{icon} {ev_name}[/{color}]")

                    if self.reasoning_collapsed:
                        content.append(f"[dim]💭 推理链路 ({len(msg.events)} 个事件) [展开: /expand][/dim]\n")
                    else:
                        content.append(f"[dim]💭 推理链路:[/dim]")
                        for line in event_lines:
                            content.append(f"  {line}")
                        content.append("")

                # 主内容用 Markdown 渲染
                if main:
                    content.append(f"[bold bright_blue]Agent:[/bold bright_blue]")
                    content.append(Markdown(main))
                    content.append("")

            content.append("")

        if not content:
            content = ["[dim]暂无消息，选择或创建一个会话开始对话[/dim]"]

        return Panel(
            "\n".join(str(c) for c in content),
            title=f"[bold bright_blue]聊天[/bold bright_blue] {self.current_session_id or ''}",
            border_style="bright_blue",
        )

    def build_layout(self) -> Layout:
        """构建整体布局"""
        layout = Layout()

        # 顶部状态栏
        header = Panel(
            Align.center(f"[bold bright_white]DevOps Agent CLI[/bold bright_white]   {self.status_text}"),
            height=3,
            border_style="bright_black",
        )

        # 主体：左侧会话列表 + 右侧聊天区
        body = Layout()
        body.split_row(
            Layout(self.build_sessions_panel(), size=30),
            Layout(self.build_chat_panel()),
        )

        # 底部输入区
        footer = Panel(
            f"[bold bright_white]> {self.input_buffer}[/bold bright_white]",
            title="[dim]Enter发送 | Ctrl+C退出 | /help 帮助[/dim]",
            border_style="bright_black",
            height=3,
        )

        layout.split_column(
            Layout(header, size=3),
            body,
            Layout(footer, size=3),
        )

        return layout

    async def send_message(self, text: str) -> None:
        """发送消息并流式接收响应"""
        if not text.strip():
            return

        # 如果没有当前会话，自动创建
        if not self.current_session_id:
            sid = await self.create_session()
            if not sid:
                return

        # 添加用户消息
        self.messages.append(Message(role="user", content=text))
        self.input_buffer = ""
        self.status_text = "发送中..."

        # 准备收集 assistant 响应
        assistant_content = ""
        assistant_events: list[dict[str, Any]] = []
        assistant_msg = Message(role="assistant", content="", events=[])
        self.messages.append(assistant_msg)

        try:
            async for event_name, payload in self.client.stream_chat(text, self.current_session_id):
                assistant_events.append({"event": event_name, **payload})

                if event_name == "output":
                    assistant_content = payload.get("reply", "")
                    assistant_msg.content = assistant_content
                    assistant_msg.events = assistant_events
                    self.status_text = "完成"

                elif event_name == "error":
                    error_msg = payload.get("error", "未知错误")
                    assistant_content = f"[red]错误: {error_msg}[/red]"
                    assistant_msg.content = assistant_content
                    assistant_msg.events = assistant_events
                    self.status_text = f"[red]出错了[/red]"

                elif event_name in ("execute", "execute_done", "analyze", "plan"):
                    # 实时更新状态
                    self.status_text = f"{EVENT_ICONS.get(event_name, '•')} {event_name}..."

                # 更新消息
                assistant_msg.events = assistant_events
                await asyncio.sleep(0.01)  # 让 UI 有机会刷新

            # 最终更新
            assistant_msg.content = assistant_content
            assistant_msg.events = assistant_events
            await self.fetch_sessions()  # 更新会话标题（后端可能自动生成）

        except Exception as e:
            assistant_msg.content = f"[red]请求异常: {e}[/red]"
            self.status_text = f"[red]失败: {e}[/red]"

    async def handle_command(self, cmd: str) -> bool:
        """处理斜杠命令，返回是否退出"""
        cmd = cmd.strip().lower()

        if cmd in ("/quit", "/exit", "/q"):
            return True

        if cmd == "/help":
            self.messages.append(
                Message(
                    role="system",
                    content="""
[bold]命令列表:[/bold]
  /help     - 显示帮助
  /quit     - 退出程序
  /new      - 创建新会话
  /delete   - 删除当前会话
  /refresh  - 刷新会话列表
  /expand   - 展开推理链路
  /collapse - 折叠推理链路
  /sessions - 显示会话列表

[bold]快捷键:[/bold]
  Ctrl+C    - 退出
  ↑/↓       - 选择会话（开发中）
""",
                )
            )
            return False

        if cmd == "/new":
            await self.create_session()
            return False

        if cmd == "/delete":
            await self.delete_current_session()
            return False

        if cmd == "/refresh":
            await self.fetch_sessions()
            return False

        if cmd == "/expand":
            self.reasoning_collapsed = False
            return False

        if cmd == "/collapse":
            self.reasoning_collapsed = True
            return False

        if cmd == "/sessions":
            await self.fetch_sessions()
            return False

        self.status_text = f"[yellow]未知命令: {cmd}[/yellow]"
        return False

    async def run(self) -> None:
        """主循环"""
        # 检查后端健康
        try:
            health = await self.client.health()
            self.status_text = f"[green]后端健康: {health.get('status', 'ok')}[/green]"
        except Exception as e:
            self.status_text = f"[red]后端连接失败: {e}[/red]"
            console.print(f"[red]无法连接到后端: {e}[/red]")
            console.print(f"[dim]请确保后端服务运行: http://localhost:8000[/dim]")
            return

        # 加载会话列表
        await self.fetch_sessions()

        console.print("[bold bright_blue]DevOps Agent CLI[/bold bright_blue]")
        console.print("[dim]基于 Rich 的终端客户端 | /help 查看命令[/dim]\n")

        # 简单的输入循环（非实时 TUI，但支持流式显示）
        while True:
            try:
                # 显示当前状态
                console.print(f"\n[dim]{self.status_text}[/dim]")

                # 显示会话列表摘要
                if self.sessions:
                    console.print("\n[bold bright_blue]会话:[/bold bright_blue]")
                    for i, s in enumerate(self.sessions[:5], 1):
                        sid = s.get("session_id", "")[:8]
                        title = s.get("title", "未命名")
                        marker = "▶" if s.get("session_id") == self.current_session_id else " "
                        console.print(f"  {marker} [{i}] {title} ({sid}...)")

                # 显示最近消息摘要（assistant 消息去掉 think 块）
                if self.messages:
                    console.print("\n[bold bright_blue]最近消息:[/bold bright_blue]")
                    for msg in self.messages[-3:]:
                        role = "你" if msg.role == "user" else "Agent"
                        if msg.role == "assistant":
                            main, _ = self.parse_think_block(msg.content)
                            content = main[:60].replace("\n", " ") if main else ""
                        else:
                            content = msg.content[:60].replace("\n", " ")
                        console.print(f"  [dim]{role}:[/dim] {content}...")

                # 获取输入
                user_input = Prompt.ask("\n[bold bright_green]你[/bold bright_green]").strip()

                if not user_input:
                    continue

                # 斜杠命令
                if user_input.startswith("/"):
                    should_exit = await self.handle_command(user_input)
                    if should_exit:
                        break
                    continue

                # 快捷键处理
                if user_input.upper() == "N":
                    await self.create_session()
                    continue
                if user_input.upper() == "D" and self.current_session_id:
                    await self.delete_current_session()
                    continue
                if user_input.upper() == "R":
                    await self.fetch_sessions()
                    continue

                # 发送消息（流式显示）
                await self._chat_with_stream(user_input)

            except KeyboardInterrupt:
                console.print("\n[yellow]再见![/yellow]")
                break
            except Exception as e:
                console.print(f"[red]错误: {e}[/red]")

        await self.client.close()

    async def _chat_with_stream(self, message: str) -> None:
        """带流式显示的对话"""
        if not self.current_session_id:
            sid = await self.create_session()
            if not sid:
                return

        # 显示用户消息
        console.print(f"\n[bold bright_green]你:[/bold bright_green] {message}")

        # 流式接收
        console.print(f"\n[bold bright_blue]Agent:[/bold bright_blue] ", end="")

        content = ""
        events = []

        with console.status("[cyan]思考中...[/cyan]", spinner="dots") as status:
            async for event_name, payload in self.client.stream_chat(message, self.current_session_id):
                events.append({"event": event_name, **payload})

                if event_name == "analyze":
                    status.update("[cyan]分析中...[/cyan]")
                elif event_name == "plan":
                    tools = payload.get("tools", [])
                    tool_names = [t.get("name", "?") for t in tools]
                    status.update(f"[cyan]计划: {', '.join(tool_names)}[/cyan]")
                elif event_name == "execute":
                    tool = payload.get("tool_name", "?")
                    status.update(f"[yellow]执行: {tool}...[/yellow]")
                elif event_name == "execute_done":
                    status.update("[green]执行完成[/green]")
                elif event_name == "output":
                    content = payload.get("reply", "")
                    status.update("[green]生成回复[/green]")
                elif event_name == "error":
                    content = f"[red]错误: {payload.get('error', '未知错误')}[/red]"

        # 显示最终回复
        if content:
            # 提取 think 块
            main, think = self.parse_think_block(content)

            if think:
                console.print(f"\n[dim]💭 思考过程: {think[:100]}...[/dim]")

            console.print(Markdown(main))

            # 保存到消息列表（简化版）
            self.messages.append(Message(role="user", content=message))
            self.messages.append(Message(role="assistant", content=content, events=events))

        # 刷新会话列表（标题可能更新）
        await self.fetch_sessions()
