"""
Original config.py from ApeCodeAI/nanoclaw-py
Source: https://github.com/ApeCodeAI/nanoclaw-py/blob/master/src/nanoclaw/config.py

KEY STRUCTURE:
- Reads from .env via python-dotenv
- Required: TELEGRAM_BOT_TOKEN, OWNER_ID, ANTHROPIC_API_KEY
- Optional: ANTHROPIC_BASE_URL, ASSISTANT_NAME, SCHEDULER_INTERVAL
- Paths: BASE_DIR, WORKSPACE_DIR, STORE_DIR, DATA_DIR, DB_PATH, STATE_FILE

OUR MODIFICATION PLAN:
- DELETE: TELEGRAM_BOT_TOKEN, OWNER_ID (no Telegram)
- RENAME/KEEP: ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL
- ADD: OPENAI_API_KEY, OPENAI_BASE_URL (dual protocol)
- ADD: LLM_PROTOCOL ("anthropic" | "openai"), LLM_MODEL_NAME
- ADD: SECURITY_* configs (protected paths, sudo whitelist, etc.)
- MODIFY: DB_PATH to point to our data directory
- ADD: DEVOPS_RUNNER_USER, COMMAND_WHITELIST_FILE
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Required
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Optional
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Ape")
SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "60"))

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
WORKSPACE_DIR = BASE_DIR / "workspace"
STORE_DIR = BASE_DIR / "store"
DATA_DIR = BASE_DIR / "data"
DB_PATH = STORE_DIR / "nanoclaw.db"
STATE_FILE = DATA_DIR / "state.json"


def get_chat_workspace(chat_id: int) -> Path:
    """Get workspace directory for a specific chat.

    Currently all chats share the same workspace (single-user mode).
    Future: Each chat can have isolated workspace for multi-user/group support.

    Example future structure:
        workspace/
        ├── chats/
        │   ├── 12345/        # user chat
        │   │   ├── CLAUDE.md
        │   │   └── conversations/
        │   └── -98765/       # group chat (negative ID)
        │       ├── CLAUDE.md
        │       └── conversations/
    """
    # Single-user mode: all chats use the same workspace
    return WORKSPACE_DIR

    # Future multi-user mode (uncomment when needed):
    # chat_dir = WORKSPACE_DIR / "chats" / str(chat_id)
    # chat_dir.mkdir(parents=True, exist_ok=True)
    # return chat_dir
