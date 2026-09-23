"""Streaming validation against the supplied sr_hex reference dataset."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CsvComparison:
    total_rows: int
    mismatches: int
    mismatch_rate: float


def _normalise_h3(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("0").str.strip()


def compare_h3_csvs(
    produced_path: Path,
    reference_path: Path,
    *,
    column: str = "h3_level8_index",
    chunksize: int = 100_000,
) -> CsvComparison:
    """Compare output and reference H3 columns without loading both files fully."""
    produced_iter = pd.read_csv(
        produced_path,
        usecols=[column],
        dtype={column: "string"},
        chunksize=chunksize,
        compression="infer",
    )
    reference_iter = pd.read_csv(
        reference_path,
        usecols=[column],
        dtype={column: "string"},
        chunksize=chunksize,
        compression="infer",
    )

    total = 0
    mismatches = 0
    for produced, reference in zip_longest(produced_iter, reference_iter):
        if produced is None or reference is None:
            raise ValueError(
                "Produced and reference CSV files have different row counts"
            )
        if len(produced) != len(reference):
            raise ValueError(
                "Produced and reference CSV chunks have different row counts"
            )
        left = _normalise_h3(produced[column]).reset_index(drop=True)
        right = _normalise_h3(reference[column]).reset_index(drop=True)
        total += len(left)
        mismatches += int((left != right).sum())

    rate = mismatches / total if total else 0.0
    return CsvComparison(total, mismatches, rate)
