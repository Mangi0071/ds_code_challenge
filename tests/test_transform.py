import pandas as pd
import pytest

from solution.transform import JoinThresholdExceeded, assign_h3_cells


def fake_latlng_to_cell(lat, lon, resolution):
    assert resolution == 8
    if (lat, lon) == (-33.9, 18.4):
        return "88195da49bfffff"
    if (lat, lon) == (-33.8, 18.5):
        return "88195da49afffff"
    return "88outside000000"


def test_missing_coordinates_are_assigned_zero():
    frame = pd.DataFrame(
        {
            "Latitude": [-33.9, None, ""],
            "Longitude": [18.4, 18.5, None],
        }
    )
    result, metrics = assign_h3_cells(
        frame,
        city_h3_indexes={"88195da49bfffff"},
        latlng_to_cell=fake_latlng_to_cell,
        max_join_failure_rate=1.0,
    )

    assert result["h3_level8_index"].tolist() == ["88195da49bfffff", "0", "0"]
    assert metrics.missing_coordinate_rows == 2
    assert metrics.join_failures == 0


def test_valid_coordinate_outside_city_is_join_failure_and_zero():
    frame = pd.DataFrame({"Latitude": [-33.8], "Longitude": [18.5]})
    result, metrics = assign_h3_cells(
        frame,
        city_h3_indexes={"88195da49bfffff"},
        latlng_to_cell=fake_latlng_to_cell,
        max_join_failure_rate=1.0,
    )

    assert result.loc[0, "h3_level8_index"] == "0"
    assert metrics.join_failures == 1
    assert metrics.join_failure_rate == 1.0


def test_join_failure_threshold_raises():
    frame = pd.DataFrame({"Latitude": [-33.8, -33.9], "Longitude": [18.5, 18.4]})
    with pytest.raises(JoinThresholdExceeded):
        assign_h3_cells(
            frame,
            city_h3_indexes={"88195da49bfffff"},
            latlng_to_cell=fake_latlng_to_cell,
            max_join_failure_rate=0.10,
        )


def test_out_of_range_coordinates_count_as_invalid_not_join_failure():
    frame = pd.DataFrame({"Latitude": [95], "Longitude": [18.4]})
    result, metrics = assign_h3_cells(
        frame,
        city_h3_indexes={"88195da49bfffff"},
        latlng_to_cell=fake_latlng_to_cell,
        max_join_failure_rate=0.0,
    )

    assert result.loc[0, "h3_level8_index"] == "0"
    assert metrics.invalid_coordinate_rows == 1
    assert metrics.join_failures == 0

def test_lowercase_city_coordinate_columns_are_supported():
    frame = pd.DataFrame(
        {"latitude": [-33.9], "longitude": [18.4]}
    )

    result, metrics = assign_h3_cells(
        frame,
        city_h3_indexes={"88195da49bfffff"},
        latlng_to_cell=fake_latlng_to_cell,
        max_join_failure_rate=1.0,
    )

    assert result["h3_level8_index"].tolist() == ["88195da49bfffff"]
    assert metrics.joined_rows == 1
