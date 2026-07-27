"""Demo defaults for Glue-to-Synapse POC presentations."""

from pathlib import Path

DEFAULT_JOB_NAME = "data_cleaning_and_lambda"
DEFAULT_SOURCE_FILE = "data_cleaning_and_lambda.py"

DEMO_STAGES: list[tuple[str, str, str]] = [
    ("SCANNING", "stage_complete", "Repository scan complete"),
    ("ANALYZING", "artifact_reused", "Understanding.md — analyzer output (cached)"),
    ("PLANNING", "artifact_reused", "MigrationPlan.md — migration plan (cached)"),
    ("AWAITING_APPROVAL", "stage_complete", "Plan pre-approved for demo"),
    ("IMPLEMENTING", "artifact_reused", "converted_code — Synapse Python (cached)"),
    ("REVIEWING", "artifact_reused", "Review.md — code review passed (cached)"),
    ("VALIDATING", "artifact_reused", "Validation.md — semantic validation (cached)"),
    ("TESTING", "stage_complete", "Output parity check on sample Medicare data"),
    ("DOCUMENTING", "artifact_reused", "README.md — migration documentation (cached)"),
    ("COMPLETE", "stage_complete", "Demo pipeline complete — zero API tokens used"),
]


def get_project_root() -> Path:
    """Return AI-SDLC repository root (parent of demo/)."""
    return Path(__file__).resolve().parent.parent


def get_default_glue_repo() -> Path:
    """Default Glue sample repo bundled with the framework."""
    return get_project_root() / "GlueRepo"


def get_sample_csv_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "medicare_sample.csv"
