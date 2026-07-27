"""Dependency graph builder for repository files."""

from pathlib import Path

from parser.models import DependencyGraph, DependencyNode


def build_dependency_graph(
    file_imports: dict[str, list[str]],
    glue_job_paths: list[str],
) -> DependencyGraph:
    """Build dependency graph from file import mappings."""
    nodes: list[DependencyNode] = []
    all_paths = set(file_imports.keys())

    for file_path, imports in file_imports.items():
        resolved_imports = _resolve_imports(file_path, imports, all_paths)
        imported_by = [
            fp for fp, imps in file_imports.items()
            if file_path in _resolve_imports(fp, imps, all_paths)
        ]
        nodes.append(
            DependencyNode(
                file_path=file_path,
                imports=resolved_imports,
                imported_by=imported_by,
            )
        )

    return DependencyGraph(nodes=nodes, glue_jobs=glue_job_paths)


def _resolve_imports(
    file_path: str,
    imports: list[str],
    all_paths: set[str],
) -> list[str]:
    """Resolve import statements to file paths within the repo."""
    resolved: list[str] = []
    file_dir = str(Path(file_path).parent)

    for imp in imports:
        # Try direct module path match
        module_path = imp.replace(".", "/") + ".py"
        if module_path in all_paths:
            resolved.append(module_path)
            continue

        # Try relative to file directory
        relative = str(Path(file_dir) / module_path)
        if relative in all_paths:
            resolved.append(relative)
            continue

        # Try as package __init__
        init_path = imp.replace(".", "/") + "/__init__.py"
        if init_path in all_paths:
            resolved.append(init_path)

    return sorted(set(resolved))
