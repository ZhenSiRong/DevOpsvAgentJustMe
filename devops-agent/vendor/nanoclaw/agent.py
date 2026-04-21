"""
Original agent.py from ApeCodeAI/nanoclaw-py
Source: https://github.com/ApeCodeAI/nanoclaw-py/blob/master/src/nanoclaw/agent.py

KEY STRUCTURE TO UNDERSTAND FOR MODIFICATION:
1. _create_tools() - defines @tool() decorated functions (MCP tools)
2. Uses claudette_agent_sdk: query(), tool(), create_sdk_mcp_server()
3. Tools: send_message, schedule_task, list_tasks, pause_task, resume_task, cancel_task
4. run_agent() / clear_session_id() - main entry points called by bot.py

OUR MODIFICATION PLAN (see Architecture_BS3Layer_v2.mmd):
- DELETE: send_message tool (Telegram-specific)
- DELETE: schedule_task/list_tasks/pause_task/resume_task/cancel_task (keep db.py functions)
- ADD: @tool() for probe.disk_usage, probe.process_list, probe.network, probe.logs
- ADD: safety validator interceptor BEFORE tool execution
- ADD: audit log writer AFTER each phase
- REPLACE: LLM backend with dual-protocol (Anthropic + OpenAI compatible)
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

from claudette_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    query,
    tool,
)
from croniter import croniter

from nanoclaw import db
from nanoclaw.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    DATA_DIR,
    STATE_FILE,
    WORKSPACE_DIR,
)

logger = logging.getLogger(__name__)
_agent_lock = asyncio.Lock()


def _create_tools(bot: Any, chat_id: int, db_path: str, notify_state: dict[str, bool] | None = None) -> list:
    @tool("send_message", "Send a message to the user on Telegram", {"text": str})
    async def send_message(args: dict[str, Any]) -> dict[str, Any]:
        await bot.send_message(chat_id=chat_id, text=args["text"])
        if notify_state is not None:
            notify_state["sent"] = True
        return {"content": [{"type": "text", "text": "Message sent."}]}

    @tool(
        "schedule_task",
        "Schedule a task. schedule_type: 'cron', 'interval', or 'once'. schedule_value: cron expression, milliseconds, or ISO timestamp.",
        {"prompt": str, "schedule_type": str, "schedule_value": str},
    )
    async def schedule_task(args: dict[str, Any]) -> dict[str, Any]:
        stype = args["schedule_type"]
        svalue = args["schedule_value"]
        now = datetime.now(timezone.utc)

        if stype == "cron":
            next_run = croniter(svalue, now).get_next(datetime).isoformat()
        elif stype == "interval":
            next_run = (now + timedelta(milliseconds=int(svalue))).isoformat()
        elif stype == "once":
            next_run = svalue
        else:
            return {
                "content": [{"type": "text", "text": f"Unknown schedule_type: {stype}"}],
                "is_error": True,
            }

        task_id = await db.create_task(db_path, chat_id, args["prompt"], stype, svalue, next_run)
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Task {task_id} scheduled. Next run: {next_run}",
                }
            ]
        }

    @tool("list_tasks", "List all scheduled tasks", {})
    async def list_tasks(args: dict[str, Any]) -> dict[str, Any]:
        tasks = await db.get_all_tasks(db_path)
        if not tasks:
            return {"content": [{"type": "text", "text": "No scheduled tasks."}]}
        lines = [f"- [{t['id']}] {t['status']} | {t['schedule_type']} | {t['schedule_value']} | {t['prompt'][:60]}" for t in tasks]
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    @tool("pause_task", "Pause a scheduled task", {"task_id": str})
    async def pause_task(args: dict[str, Any]) -> dict[str, Any]:
        ok = await db.update_task_status(db_path, args["task_id"], "paused")
        msg = f"Task {args['task_id']} paused." if ok else f"Task {args['task_id']} not found."
        return {"content": [{"type": "text", "text": msg}]}

    @tool("resume_task", "Resume a paused task", {"task_id": str})
    async def resume_task(args: dict[str, Any]) -> dict[str, Any]:
        ok = await db.update_task_status(db_path, args["task_id"], "active")
        msg = f"Task {args['task_id']} resumed." if ok else f"Task {args['task_id']} not found."
        return {"content": [{"type": "text", "text": msg}]}

    @tool("cancel_task", "Cancel and delete a scheduled task", {"task_id": str})
    async def cancel_task(args: dict[str, Any]) -> dict[str, Any]:
        ok = await db.delete_task(db_path, args["task_id"])
        msg = f"Task {args['task_id']} cancelled." if ok else f"Task {args['task_id']} not found."
        return {"content": [{"type": "text", "text": msg}]}

    return [send_message, schedule_task, list_tasks, pause_task, resume_task, cancel_task]


_session_id: str | None = None


def get_session_id() -> str | None:
    return _session_id


def clear_session_id() -> None:
    global _session_id
    _session_id = None


def _load_session_id() -> str | None:
    global _session_id
    if _session_id is not None:
        return _session_id
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        _session_id = data.get("session_id")
        return _session_id
    except (json.JSONDecodeError, OSError):
        return None


def _save_session_id(sid: str) -> None:
    global _session_id
    _session_id = sid
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"session_id": sid}))


async def run_agent(user_input: str, bot: Any, chat_id: int, db_path: str) -> str:
    """Main agent entry point. Called by bot.py _handle_message()."""
    global _session_id
    tools = _create_tools(bot, chat_id, db_path)
    session_id = _load_session_id()

    options = ClaudeAgentOptions(
        api_key=ANTHROPIC_API_KEY,
        base_url=ANTHROPIC_BASE_URL,
    )

    full_response = []
    async for message in query(
        user_input,
        tools=tools,
        session_id=session_id,
        options=options,
    ):
        if isinstance(message, (AssistantMessage, ResultMessage)):
            for block in message.content:
                if isinstance(block, TextBlock):
                    full_response.append(block.text)
                    # Save session ID for conversation continuity
                    if hasattr(message, 'session_id') and message.session_id:
                        _save_session_id(message.session_id)

    return "\n".join(full_response) if full_response else "No response generated."
