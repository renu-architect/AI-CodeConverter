"""AST extraction from Python source files."""

import ast
from pathlib import Path
from typing import Any

from parser.glue_detector import detect_glue_calls, detect_glue_imports
from parser.models import ASTSummary


def extract_ast(file_path: Path) -> ASTSummary:
    """Parse Python file and extract AST summary."""
    source = file_path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(file_path))
    line_count = len(source.splitlines())

    imports = _extract_imports(tree)
    functions = _extract_functions(tree)
    classes = _extract_classes(tree)
    variables = _extract_variables(tree)
    glue_api_calls = detect_glue_calls(tree, source)

    return ASTSummary(
        imports=imports,
        functions=functions,
        classes=classes,
        variables=variables,
        glue_api_calls=glue_api_calls,
        line_count=line_count,
    )


def _extract_imports(tree: ast.AST) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}" if module else alias.name)
    return sorted(set(imports))


def _extract_functions(tree: ast.AST) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = _extract_calls(node)
            functions.append(
                {
                    "name": node.name,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                    "calls": calls,
                }
            )
    return functions


def _extract_classes(tree: ast.AST) -> list[dict[str, Any]]:
    classes: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                n.name
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes.append(
                {
                    "name": node.name,
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                    "methods": methods,
                }
            )
    return classes


def _extract_variables(tree: ast.AST) -> list[str]:
    variables: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    variables.append(target.id)
    return sorted(set(variables))


def _extract_calls(node: ast.AST) -> list[str]:
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            call_name = _get_call_name(child)
            if call_name:
                calls.append(call_name)
    return sorted(set(calls))


def _get_call_name(node: ast.Call) -> str | None:
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
