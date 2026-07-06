import json
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

import apps.shail.db

logger = logging.getLogger(__name__)

def init_ghost_sessions_db() -> None:
    """Initialize the ghost_sessions table and its indexes."""
    with apps.shail.db.get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ghost_sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                intent_text TEXT,
                total_steps INTEGER,
                completed_steps INTEGER,
                status TEXT,
                clicky_log TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ghost_sessions_created_at ON ghost_sessions(created_at);
            CREATE INDEX IF NOT EXISTS idx_ghost_sessions_status ON ghost_sessions(status);
        """)

def create_session(total_steps: int, intent_text: Optional[str] = None) -> str:
    """Creates a new ghost_session and returns its unique session_id."""
    session_id = uuid.uuid4().hex
    created_at = datetime.utcnow().isoformat()
    with apps.shail.db.get_db() as conn:
        conn.execute(
            """
            INSERT INTO ghost_sessions (session_id, created_at, intent_text, total_steps, completed_steps, status, clicky_log)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, created_at, intent_text, total_steps, 0, "in_progress", "[]")
        )
    return session_id

def update_session_progress(session_id: str, completed_steps: int) -> None:
    """Updates the completed_steps count for the given session_id."""
    with apps.shail.db.get_db() as conn:
        conn.execute(
            "UPDATE ghost_sessions SET completed_steps = ? WHERE session_id = ?",
            (completed_steps, session_id)
        )

def end_session(session_id: str, status: str, clicky_log: List[Dict[str, Any]]) -> None:
    """Ends the session, updating status and persisting the clicky event log."""
    log_json = json.dumps(clicky_log)
    with apps.shail.db.get_db() as conn:
        conn.execute(
            "UPDATE ghost_sessions SET status = ?, clicky_log = ? WHERE session_id = ?",
            (status, log_json, session_id)
        )
