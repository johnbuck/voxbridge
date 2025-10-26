"""
VoxBridge 2.0 - Database Module

Exports models, session management, and utilities.

Usage:
    from src.database import Agent, Session, Conversation
    from src.database import get_db_session, init_db
"""

from src.database.models import Agent, Session, Conversation, Base
from src.database.session import (
    get_db_session,
    get_db_session_dependency,
    init_db,
    drop_db,
    check_db_connection,
)

__all__ = [
    # Models
    "Agent",
    "Session",
    "Conversation",
    "Base",
    # Session management
    "get_db_session",
    "get_db_session_dependency",
    "init_db",
    "drop_db",
    "check_db_connection",
]
