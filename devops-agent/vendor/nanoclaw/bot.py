"""
Original bot.py from ApeCodeAI/nanoclaw-py
Source: https://github.com/ApeCodeAI/nanoclaw-py/blob/master/src/nanoclaw/bot.py

KEY STRUCTURE:
- Telegram Bot entry point using python-telegram-bot
- _is_owner(): permission check against OWNER_ID
- _start(), _clear(): command handlers
- _handle_message(): core pipeline -> run_agent() -> archive_exchange() -> reply
- setup_bot(): assembles Application with handlers
- _post_init(): starts scheduler on bot startup

OUR MODIFICATION PLAN:
- DELETE ENTIRELY - Replace with FastAPI main.py (B/S architecture)
- Reference _handle_message() flow for understanding the agent call pattern:
  user_text -> run_agent(user_text, ...) -> response -> archive -> reply
  This maps to our: POST /chat -> agent.run() -> SSE stream -> audit log
"""

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from nanoclaw.agent import run_agent, clear_session_id
from nanoclaw.conversations import archive_exchange
from nanoclaw.config import ASSISTANT_NAME, DB_PATH, OWNER_ID, TELEGRAM_BOT_TOKEN
from nanoclaw.scheduler import setup_schedulers

logger = logging.getLogger(__name__)
_TELEGRAM_MAX_LENGTH = 4096


def _is_owner(update: Update) -> bool:
    """Permission check: only OWNER_ID can use this bot."""
    return update.effective_user is not None and update.effective_user.id == OWNER_ID


async def _start(update: Update, context) -> None:
    """Handle /start command: owner only."""
    if not _is_owner(update):
        return
    await update.message.reply_text(
        f"Hi! I'm {ASSISTANT_NAME}, your personal AI assistant. Send me a message to get started.\n\n"
        "Commands:\n"
        "/clear - Reset conversation session"
    )


async def _clear(update: Update, context) -> None:
    """Handle /clear command: clear session state."""
    if not _is_owner(update):
        return
    clear_session_id()
    await update.message.reply_text("Session cleared. Starting fresh!")


async def _handle_message(update: Update, context) -> None:
    """Core message handler: text -> AI agent -> archive -> reply."""
    if not _is_owner(update) or not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_text = update.message.text

    # Show "typing..." indicator
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Call Agent for response
    response = await run_agent(user_text, context.bot, chat_id, str(DB_PATH))

    # Archive conversation for long-term memory
    await archive_exchange(user_text, response, chat_id)

    # Handle Telegram's 4096 char limit by splitting
    for i in range(0, len(response), _TELEGRAM_MAX_LENGTH):
        chunk = response[i : i + _TELEGRAM_MAX_LENGTH]
        await update.message.reply_text(chunk)


async def _post_init(application: Application) -> None:
    """Post-init hook: start scheduler."""
    scheduler = setup_schedulers(application.bot, str(DB_PATH))
    scheduler.start()
    logger.info("Scheduler started")


def setup_bot() -> Application:
    """Bot builder: assemble handlers and return Application."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("clear", _clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    return app
