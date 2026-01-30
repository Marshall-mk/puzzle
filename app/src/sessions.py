"""
Session management for the eHealth Puzzle Game
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict

# Session storage
game_sessions: Dict[str, Dict] = {}
session_timeouts: Dict[str, datetime] = {}

SESSION_TIMEOUT_MINUTES = 60


def get_or_create_session(session_id: Optional[str] = None) -> str:
    """
    Get existing session or create a new one.
    Returns the session ID.
    """
    if session_id and session_id in game_sessions:
        # Update timeout
        session_timeouts[session_id] = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        return session_id

    # Create new session
    new_session_id = str(uuid.uuid4())
    game_sessions[new_session_id] = {
        "original_positions": None,
        "shuffled_positions": None,
        "patches": None,
        "current_level": "level_1",
        "current_image_name": None,
        "start_time": None
    }
    session_timeouts[new_session_id] = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    return new_session_id


def get_session(session_id: str) -> Optional[Dict]:
    """Get a session by ID."""
    return game_sessions.get(session_id)


def cleanup_expired_sessions():
    """Remove expired sessions to free memory."""
    now = datetime.now()
    expired = [sid for sid, timeout in session_timeouts.items() if timeout < now]

    for sid in expired:
        game_sessions.pop(sid, None)
        session_timeouts.pop(sid, None)

    if expired:
        print(f"Cleaned up {len(expired)} expired sessions")


def clear_session(session_id: str):
    """Clear a specific session."""
    game_sessions.pop(session_id, None)
    session_timeouts.pop(session_id, None)
