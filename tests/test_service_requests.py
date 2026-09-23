import pandas as pd
import pytest

from solution.service_requests import process_service_requests
from solution.transform import JoinThresholdExceeded


def fake_latlng_to_cell(lat, lon, resolution):
    if (lat, lon) == (-33.9, 18.4):
        return "88195da49bfffff"
    return "88195da49afffff"


def test_process_service_requests_streams_chunks_and_aggregates_metrics(tmp_path):
    input_path = tmp_path / "sr.csv.gz"
    output_path = tmp_path / "out.csv.gz"
    pd.DataFrame(
        {
            "Latitude": [-33.9, -33.8, None],
            "Longitude": [18.4, 18.5, 18.4],
            "value": [1, 2, 3],
        }
    ).to_csv(input_path, index=False, compression="gzip")

    metrics = process_service_requests(
        input_path,
        output_path,
        city_h3_indexes={"88195da49bfffff"},
        latlng_to_cell=fake_latlng_to_cell,
        chunksize=2,
        max_join_failure_rate=0.6,
    )

    result = pd.read_csv(output_path, dtype={"h3_level8_index": "string"})
    assert result["h3_level8_index"].tolist() == ["88195da49bfffff", "0", "0"]
    assert metrics.total_rows == 3
    assert metrics.join_failures == 1
    assert metrics.missing_coordinate_rows == 1
    assert metrics.join_failure_rate == 0.5


def test_process_service_requests_applies_threshold_to_global_rate(tmp_path):
    input_path = tmp_path / "sr.csv.gz"
    output_path = tmp_path / "out.csv.gz"
    pd.DataFrame(
        {"Latitude": [-33.9, -33.8], "Longitude": [18.4, 18.5]}
    ).to_csv(input_path, index=False, compression="gzip")

    with pytest.raises(JoinThresholdExceeded):
        process_service_requests(
            input_path,
            output_path,
            city_h3_indexes={"88195da49bfffff"},
            latlng_to_cell=fake_latlng_to_cell,
            chunksize=1,
            max_join_failure_rate=0.4,
        )
