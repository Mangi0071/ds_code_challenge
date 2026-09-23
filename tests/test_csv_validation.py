import pandas as pd

from solution.csv_validation import compare_h3_csvs


def test_compare_h3_csvs_reports_exact_match(tmp_path):
    produced = tmp_path / "produced.csv.gz"
    reference = tmp_path / "reference.csv.gz"
    frame = pd.DataFrame({"id": [1, 2], "h3_level8_index": ["88195da49bfffff", "0"]})
    frame.to_csv(produced, index=False, compression="gzip")
    frame.to_csv(reference, index=False, compression="gzip")

    result = compare_h3_csvs(produced, reference, chunksize=1)

    assert result.total_rows == 2
    assert result.mismatches == 0
    assert result.mismatch_rate == 0.0


def test_compare_h3_csvs_reports_mismatch(tmp_path):
    produced = tmp_path / "produced.csv.gz"
    reference = tmp_path / "reference.csv.gz"
    pd.DataFrame({"h3_level8_index": ["88195da49bfffff", "0"]}).to_csv(
        produced, index=False, compression="gzip"
    )
    pd.DataFrame({"h3_level8_index": ["88195da49afffff", "0"]}).to_csv(
        reference, index=False, compression="gzip"
    )

    result = compare_h3_csvs(produced, reference, chunksize=10)

    assert result.mismatches == 1
    assert result.mismatch_rate == 0.5
