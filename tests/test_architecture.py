"""Architecture import boundary enforcement tests."""

import ast
import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent

FORBIDDEN_IMPORTS = {
    "agents": ["anthropic", "agents."],
    "parser": ["gateway", "anthropic"],
    "frontend": ["gateway", "agents.", "anthropic"],
    "orchestrator": [],
}

ALLOWED_GATEWAY_IMPORTS = ["anthropic"]


def _get_python_files(directory: str) -> list[Path]:
    base = PROJECT_ROOT / directory
    if not base.exists():
        return []
    return [f for f in base.rglob("*.py") if "__pycache__" not in str(f)]


def _get_imports(file_path: Path) -> list[str]:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_no_anthropic_outside_gateway():
    """Only gateway/ may import anthropic."""
    for directory in ["agents", "parser", "orchestrator", "frontend", "artifacts", "knowledge", "history"]:
        for file_path in _get_python_files(directory):
            imports = _get_imports(file_path)
            for imp in imports:
                assert "anthropic" not in imp, (
                    f"{file_path.relative_to(PROJECT_ROOT)} imports anthropic — "
                    f"only gateway/ is allowed"
                )


def test_no_agent_to_agent_imports():
    """Agents must not import other agents."""
    agent_dirs = list((PROJECT_ROOT / "agents").glob("*/"))
    for agent_dir in agent_dirs:
        if not agent_dir.is_dir():
            continue
        for file_path in _get_python_files(str(agent_dir.relative_to(PROJECT_ROOT))):
            imports = _get_imports(file_path)
            for imp in imports:
                if imp.startswith("agents.") and not imp.startswith(f"agents.{agent_dir.name}"):
                    if imp != "agents.base_agent":
                        assert False, (
                            f"{file_path.relative_to(PROJECT_ROOT)} imports {imp} — "
                            f"agent-to-agent imports forbidden"
                        )


def test_parser_no_gateway():
    """Scanner must not import gateway."""
    for file_path in _get_python_files("parser"):
        imports = _get_imports(file_path)
        for imp in imports:
            assert "gateway" not in imp, (
                f"{file_path.relative_to(PROJECT_ROOT)} imports gateway — "
                f"parser must be deterministic"
            )
