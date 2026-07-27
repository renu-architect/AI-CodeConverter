"""Complexity scoring for Glue jobs (0-100 scale)."""

from parser.models import ASTSummary


def score_complexity(
    ast_summary: ASTSummary,
    sql_file_count: int = 0,
    has_error_handling: bool = False,
) -> float:
    """Calculate complexity score from AST summary and metadata."""
    loc_score = _score_loc(ast_summary.line_count)
    glue_api_score = _score_glue_apis(ast_summary.glue_api_calls)
    transform_score = _score_transforms(ast_summary)
    deps_score = _score_dependencies(ast_summary.imports)
    sql_score = _score_sql(sql_file_count)
    error_score = 10.0 if has_error_handling else 0.0

    total = (
        loc_score * 0.20
        + glue_api_score * 0.25
        + transform_score * 0.20
        + deps_score * 0.15
        + sql_score * 0.10
        + error_score * 0.10
    )
    return round(min(total, 100.0), 1)


def _score_loc(line_count: int) -> float:
    if line_count <= 500:
        return 20.0
    if line_count <= 1500:
        return 50.0
    return 80.0


def _score_glue_apis(glue_calls: list[dict]) -> float:
    unique_apis = {call["api"] for call in glue_calls}
    return min(len(unique_apis) * 5.0, 100.0)


def _score_transforms(ast_summary: ASTSummary) -> float:
    transform_keywords = {
        "join", "filter", "groupBy", "agg", "ApplyMapping",
        "ResolveChoice", "map", "flatMap", "select", "where",
    }
    count = 0
    for func in ast_summary.functions:
        for call in func.get("calls", []):
            if any(kw.lower() in call.lower() for kw in transform_keywords):
                count += 1
    return min(count * 10.0, 100.0)


def _score_dependencies(imports: list[str]) -> float:
    external = [i for i in imports if not i.startswith(("awsglue", "pyspark"))]
    return min(len(external) * 5.0, 100.0)


def _score_sql(sql_file_count: int) -> float:
    if sql_file_count == 0:
        return 0.0
    return min(sql_file_count * 20.0, 100.0)


def has_error_handling(ast_summary: ASTSummary) -> bool:
    """Check if AST indicates try/except usage (via function call patterns)."""
    error_keywords = {"try", "except", "raise", "Exception"}
    for func in ast_summary.functions:
        for call in func.get("calls", []):
            if any(kw in call for kw in error_keywords):
                return True
    return False
