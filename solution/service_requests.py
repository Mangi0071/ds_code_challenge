"""Chunked service-request processing for Section 2."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from .transform import JoinMetrics, JoinThresholdExceeded, assign_h3_cells


def process_service_requests(
    input_path: Path,
    output_path: Path,
    *,
    city_h3_indexes: set[str],
    latlng_to_cell: Callable[[float, float, int], str],
    chunksize: int,
    max_join_failure_rate: float,
) -> JoinMetrics:
    """Transform the source CSV in chunks and enforce a global failure threshold."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    totals = {
        "total_rows": 0,
        "missing_coordinate_rows": 0,
        "invalid_coordinate_rows": 0,
        "joined_rows": 0,
        "join_failures": 0,
    }

    first = True
    for chunk in pd.read_csv(
        input_path,
        chunksize=chunksize,
        compression="infer",
        low_memory=False,
    ):
        transformed, metrics = assign_h3_cells(
            chunk,
            city_h3_indexes=city_h3_indexes,
            latlng_to_cell=latlng_to_cell,
            max_join_failure_rate=1.0,
        )
        for key in totals:
            totals[key] += getattr(metrics, key)
        transformed.to_csv(
            output_path,
            mode="wt" if first else "at",
            header=first,
            index=False,
            compression="gzip",
        )
        first = False

    valid_rows = totals["joined_rows"] + totals["join_failures"]
    failure_rate = totals["join_failures"] / valid_rows if valid_rows else 0.0
    metrics = JoinMetrics(**totals, join_failure_rate=failure_rate)

    if failure_rate > max_join_failure_rate:
        raise JoinThresholdExceeded(
            f"Global join failure rate {failure_rate:.2%} exceeds threshold "
            f"{max_join_failure_rate:.2%}"
        )
    return metrics
