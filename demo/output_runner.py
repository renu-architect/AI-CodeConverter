"""Run Glue vs Synapse transforms on sample data and compare outputs (no Spark)."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from demo.constants import get_sample_csv_path


class OutputRow(BaseModel):
    """Single flattened output record for side-by-side display."""

    drg: str
    rr: str
    provider_id: int | None
    provider_name: str
    provider_city: str
    provider_state: str
    provider_zip: int | None
    charges_covered: float | None
    charges_total_pay: float | None
    charges_medicare_pay: float | None


class OutputComparisonReport(BaseModel):
    """Result of running sample data through Glue and Synapse logic."""

    job_name: str
    input_rows: int
    glue_output_rows: int
    synapse_output_rows: int
    matching_rows: int
    match_pct: float
    status: str
    message: str
    input_preview: list[dict[str, str]] = Field(default_factory=list)
    glue_output: list[dict[str, Any]] = Field(default_factory=list)
    synapse_output: list[dict[str, Any]] = Field(default_factory=list)
    diff_summary: list[str] = Field(default_factory=list)


def _parse_long(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _parse_double(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _glue_strip_currency(value: str | None) -> str | None:
    """Glue lambda x[1:] — remove first character."""
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    return text[1:].strip()


def _synapse_strip_currency(value: str | None) -> str | None:
    """Synapse regexp_replace leading $."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return re.sub(r"^\$", "", text).strip()


def _to_output_row(
    row: dict[str, str],
    *,
    strip_fn,
) -> OutputRow | None:
    provider_id = _parse_long(row.get("provider id"))
    if provider_id is None:
        return None

    acc = strip_fn(row.get("average covered charges"))
    atp = strip_fn(row.get("average total payments"))
    amp = strip_fn(row.get("average medicare payments"))

    return OutputRow(
        drg=str(row.get("drg definition", "")).strip(),
        rr=str(row.get("hospital referral region description", "") or "").strip(),
        provider_id=provider_id,
        provider_name=str(row.get("provider name", "")).strip(),
        provider_city=str(row.get("provider city", "")).strip(),
        provider_state=str(row.get("provider state", "")).strip(),
        provider_zip=_parse_long(row.get("provider zip code")),
        charges_covered=_parse_double(acc),
        charges_total_pay=_parse_double(atp),
        charges_medicare_pay=_parse_double(amp),
    )


def load_sample_rows(csv_path: Path | None = None) -> list[dict[str, str]]:
    path = csv_path or get_sample_csv_path()
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def run_glue_transform(rows: list[dict[str, str]]) -> list[OutputRow]:
    """Port of Glue data_cleaning_and_lambda.py transform chain."""
    output: list[OutputRow] = []
    for row in rows:
        record = _to_output_row(row, strip_fn=_glue_strip_currency)
        if record is not None:
            output.append(record)
    output.sort(key=lambda r: (r.provider_id or 0, r.drg))
    return output


def run_synapse_transform(rows: list[dict[str, str]]) -> list[OutputRow]:
    """Port of Synapse v7 pipeline (resolve → filter → strip → nest)."""
    output: list[OutputRow] = []
    for row in rows:
        record = _to_output_row(row, strip_fn=_synapse_strip_currency)
        if record is not None:
            output.append(record)
    output.sort(key=lambda r: (r.provider_id or 0, r.drg))
    return output


def _row_key(row: OutputRow) -> tuple[Any, ...]:
    return (
        row.drg,
        row.rr,
        row.provider_id,
        row.provider_name,
        row.provider_city,
        row.provider_state,
        row.provider_zip,
        row.charges_covered,
        row.charges_total_pay,
        row.charges_medicare_pay,
    )


def build_output_comparison(
    job_name: str = "data_cleaning_and_lambda",
    csv_path: Path | None = None,
) -> OutputComparisonReport:
    """Execute both pipelines on sample data and compare flattened outputs."""
    input_rows = load_sample_rows(csv_path)
    glue_rows = run_glue_transform(input_rows)
    synapse_rows = run_synapse_transform(input_rows)

    glue_keys = {_row_key(r) for r in glue_rows}
    synapse_keys = {_row_key(r) for r in synapse_rows}
    matching = len(glue_keys & synapse_keys)
    total = max(len(glue_keys), len(synapse_keys), 1)
    match_pct = round(matching / total * 100, 1)

    diff_summary: list[str] = []
    if len(glue_rows) != len(synapse_rows):
        diff_summary.append(
            f"Row count differs: Glue={len(glue_rows)}, Synapse={len(synapse_rows)}"
        )
    only_glue = glue_keys - synapse_keys
    only_synapse = synapse_keys - glue_keys
    if only_glue:
        diff_summary.append(f"{len(only_glue)} row(s) only in Glue output")
    if only_synapse:
        diff_summary.append(f"{len(only_synapse)} row(s) only in Synapse output")
    if not diff_summary:
        diff_summary.append("All output rows match between Glue and Synapse transforms")

    status = "PASS" if match_pct == 100.0 and len(glue_rows) == len(synapse_rows) else "PARTIAL"
    message = (
        f"Sample data parity: {match_pct:.0f}% — "
        f"{matching}/{total} output records match between Glue and Synapse logic."
    )

    return OutputComparisonReport(
        job_name=job_name,
        input_rows=len(input_rows),
        glue_output_rows=len(glue_rows),
        synapse_output_rows=len(synapse_rows),
        matching_rows=matching,
        match_pct=match_pct,
        status=status,
        message=message,
        input_preview=input_rows[:10],
        glue_output=[r.model_dump() for r in glue_rows],
        synapse_output=[r.model_dump() for r in synapse_rows],
        diff_summary=diff_summary,
    )
