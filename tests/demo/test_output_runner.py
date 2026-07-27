"""Tests for demo output parity runner."""

from demo.output_runner import build_output_comparison, run_glue_transform, run_synapse_transform


def test_sample_data_produces_matching_outputs():
    report = build_output_comparison()
    assert report.input_rows == 5
    assert report.glue_output_rows == 4  # bad-id row dropped
    assert report.synapse_output_rows == 4
    assert report.match_pct == 100.0
    assert report.status == "PASS"


def test_invalid_provider_id_excluded():
    report = build_output_comparison()
    glue_ids = {row["provider_id"] for row in report.glue_output}
    assert 100001 in glue_ids
    assert all(pid is not None for pid in glue_ids)


def test_glue_and_synapse_row_counts_match():
    from demo.output_runner import load_sample_rows

    rows = load_sample_rows()
    assert len(run_glue_transform(rows)) == len(run_synapse_transform(rows))
