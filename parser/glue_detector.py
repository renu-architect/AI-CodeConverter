"""Glue job detection from Python AST."""

import ast
import re

GLUE_IMPORTS = [
    "awsglue.transforms",
    "awsglue.utils",
    "awsglue.context",
    "awsglue.job",
    "awsglue.dynamicframe",
]

GLUE_CALLS = [
    "GlueContext",
    "DynamicFrame",
    "ApplyMapping",
    "ResolveChoice",
    "DropNullFields",
    "getResolvedOptions",
    "Job.init",
    "Job.commit",
    "create_dynamic_frame",
    "write_dynamic_frame",
    "from_catalog",
    "from_options",
]


def detect_glue_imports(imports: list[str]) -> bool:
    """Check if any imports indicate a Glue job."""
    for imp in imports:
        for glue_imp in GLUE_IMPORTS:
            if imp.startswith(glue_imp):
                return True
    return False


def detect_glue_calls(tree: ast.AST, source: str) -> list[dict]:
    """Detect Glue API calls in AST."""
    calls: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _get_full_call_name(node)
            if call_name and _is_glue_call(call_name):
                args_summary = _summarize_args(node)
                calls.append(
                    {
                        "api": call_name,
                        "line": node.lineno,
                        "args_summary": args_summary,
                    }
                )
    return calls


def is_glue_job(imports: list[str], glue_calls: list[dict]) -> bool:
    """Determine if file is a Glue job based on imports and API calls."""
    return detect_glue_imports(imports) or len(glue_calls) > 0


def _is_glue_call(call_name: str) -> bool:
    for glue_call in GLUE_CALLS:
        if glue_call in call_name or call_name.endswith(glue_call):
            return True
    return False


def _get_full_call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        parts: list[str] = []
        current: ast.expr = node.func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    return None


def _summarize_args(node: ast.Call) -> str:
    """Create brief summary of call arguments."""
    parts: list[str] = []
    for arg in node.args[:3]:
        if isinstance(arg, ast.Constant):
            parts.append(str(arg.value)[:50])
        elif isinstance(arg, ast.Name):
            parts.append(arg.id)
        elif isinstance(arg, ast.Attribute):
            parts.append(_get_full_call_name(ast.Call(func=arg, args=[], keywords=[])) or "")
    for kw in node.keywords[:3]:
        if isinstance(kw.value, ast.Constant):
            parts.append(f"{kw.arg}={kw.value.value}")
        elif isinstance(kw.value, ast.Name):
            parts.append(f"{kw.arg}={kw.value.id}")
    return ", ".join(parts)[:100]
