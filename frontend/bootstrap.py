"""Add project root and frontend directory to sys.path for Streamlit."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = Path(__file__).resolve().parent


def setup_paths() -> None:
    """Ensure imports resolve for `demo`, `utils`, `parser`, and `demo_helpers`."""
    for path in (PROJECT_ROOT, FRONTEND_DIR):
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)


# Run on import so helper modules can safely import project packages.
setup_paths()
