"""Database initialization and session management."""

from pathlib import Path

from history.models import init_db as _init_db


def init_db(database_url: str):
    """Initialize database, creating parent directories for SQLite."""
    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return _init_db(database_url)
