"""
Original conversations.py from ApeCodeAI/nanoclaw-py
Source: https://github.com/ApeCodeAI/nanoclaw-py/blob/master/src/nanoclaw/conversations.py

KEY STRUCTURE:
- File-based conversation archival (not DB)
- Stores in workspace/conversations/YYYY-MM-DD.md format
- archive_exchange(): appends user/assistant exchange to daily file
- Simple long-term memory via markdown files

OUR MODIFICATION PLAN:
- REPLACE with DB-based conversation storage (sessions + messages tables)
- Keep file-based archival as optional secondary memory
- Our audit_logs table serves as the primary structured trail
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from nanoclaw.config import WORKSPACE_DIR

logger = logging.getLogger(__name__)

CONVERSATIONS_DIR = WORKSPACE_DIR / "conversations"


def ensure_conversations_dir() -> None:
    """Create conversations directory if it doesn't exist."""
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)


def _get_today_file() -> Path:
    """Get the conversation file for today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return CONVERSATIONS_DIR / f"{today}.md"


async def archive_exchange(user_message: str, assistant_response: str, chat_id: int) -> None:
    """Archive a single user-assistant exchange to today's conversation file.

    Format:
        # HH:MM:SS UTC

        **User**: <message>

        **Ape**: <response>

        ---
    """
    ensure_conversations_dir()

    filepath = _get_today_file()
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    # Build the exchange entry
    entry = f"""# {timestamp}

**User**: {user_message**

**Ape**: {assistant_response}

---

"""

    # Append to file (create if doesn't exist)
    try:
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
        else:
            # Create file with header
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            content = f"# Conversations - {date_str}\n\n"

        content += entry
        filepath.write_text(content, encoding="utf-8")
        logger.debug("Archived exchange to %s", filepath)
    except Exception:
        logger.exception("Failed to archive exchange to %s", filepath)
