"""Environment variable loading from .env files."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_NAMES = (".env",)


def get_env_file_paths() -> list[Path]:
    """Return candidate .env file paths in load order."""
    paths = [PROJECT_ROOT / ".env"]
    config_dir = os.getenv("AI_SDLC_CONFIG", "config")
    paths.append(Path(config_dir) / ".env")
    return paths


def load_env() -> Path | None:
    """Load environment variables from the first .env file found.

    Search order:
    1. Project root: .env
    2. config/.env (or AI_SDLC_CONFIG/.env)

    Existing environment variables are not overwritten.

    Returns the path of the loaded file, or None if no file exists.
    """
    for env_path in get_env_file_paths():
        if env_path.exists():
            load_dotenv(env_path, override=False)
            return env_path
    return None


def get_api_key() -> str:
    """Return the Anthropic API key from environment.

    Loads .env files first if not already loaded.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        load_env()
    return os.getenv("ANTHROPIC_API_KEY", "")
