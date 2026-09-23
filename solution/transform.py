"""Section 2 transformation: assign service requests to City H3 cells."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


class JoinThresholdExceeded(RuntimeError):
    """Raised when valid coordinates fail the City-hex membership check too often."""


@dataclass(frozen=True)
class JoinMetrics:
    total_rows: int
    missing_coordinate_rows: int
    invalid_coordinate_rows: int
    joined_rows: int
    join_failures: int
    join_failure_rate: float


def _parse_coordinate(value: object) -> float | None:
    if (
        value is None
        or pd.isna(value)
        or (isinstance(value, str) and not value.strip())
    ):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def assign_h3_cells(
    frame: pd.DataFrame,
    *,
    city_h3_indexes: set[str],
    latlng_to_cell: Callable[[float, float, int], str],
    max_join_failure_rate: float,
    resolution: int = 8,
    latitude_column: str = "Latitude",
    longitude_column: str = "Longitude",
    output_column: str = "h3_level8_index",
) -> tuple[pd.DataFrame, JoinMetrics]:
    """Assign each request to a resolution-8 City H3 cell.

    Empty coordinates and invalid coordinate values are set to ``0``. Valid
    coordinates whose H3 cell is outside the supplied City index set are also
    set to ``0`` and counted as join failures.
    """
    result = frame.copy()

    # Resolve coordinate columns case-insensitively so the transformation
    # works with both documented-style names and the actual City source data.
    columns_by_lower = {str(column).lower(): column for column in result.columns}

    if latitude_column not in result.columns:
        latitude_column = columns_by_lower.get(latitude_column.lower(), latitude_column)

    if longitude_column not in result.columns:
        longitude_column = columns_by_lower.get(longitude_column.lower(), longitude_column)

    output: list[str] = []
    missing = 0
    invalid = 0
    joined = 0
    join_failures = 0

    for lat_raw, lon_raw in zip(result[latitude_column], result[longitude_column]):
        lat = _parse_coordinate(lat_raw)
        lon = _parse_coordinate(lon_raw)

        if lat is None or lon is None:
            missing += 1
            output.append("0")
            continue

        if (
            pd.isna(lat)
            or pd.isna(lon)
            or not (-90 <= lat <= 90)
            or not (-180 <= lon <= 180)
        ):
            invalid += 1
            output.append("0")
            continue

        cell = str(latlng_to_cell(lat, lon, resolution))
        if cell in city_h3_indexes:
            joined += 1
            output.append(cell)
        else:
            join_failures += 1
            output.append("0")

    result[output_column] = output
    valid_coordinate_rows = joined + join_failures
    failure_rate = (
        join_failures / valid_coordinate_rows if valid_coordinate_rows else 0.0
    )

    metrics = JoinMetrics(
        total_rows=len(result),
        missing_coordinate_rows=missing,
        invalid_coordinate_rows=invalid,
        joined_rows=joined,
        join_failures=join_failures,
        join_failure_rate=failure_rate,
    )

    if failure_rate > max_join_failure_rate:
        raise JoinThresholdExceeded(
            f"Join failure rate {failure_rate:.2%} exceeds threshold "
            f"{max_join_failure_rate:.2%}"
        )

    return result, metrics
