"""Utilities for querying nested GeoJSON with AWS S3 Select."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any


def quote_identifier(value: str) -> str:
    """Quote an S3 Select JSON attribute name safely."""
    return '"' + value.replace('"', '""') + '"'


def build_resolution_query(
    resolution_property: str,
    resolution: int = 8,
    *,
    value_is_string: bool = False,
) -> str:
    """Build the S3 Select query for one GeoJSON H3 resolution."""
    prop = quote_identifier(resolution_property)
    value = f"\'{int(resolution)}\'" if value_is_string else str(int(resolution))
    return (
        "SELECT * FROM S3Object[*].features[*] AS f "
        f"WHERE f.properties.{prop} = {value}"
    )


def parse_select_payload(payload: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield JSON records from the chunked event stream returned by S3 Select.

    Record delimiters can be split across event chunks, so parsing is buffered.
    """
    buffer = b""
    for event in payload:
        records = event.get("Records")
        if not records:
            continue
        buffer += records.get("Payload", b"")
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if line.strip():
                yield json.loads(line)

    if buffer.strip():
        yield json.loads(buffer)

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectStats:
    bytes_scanned: int = 0
    bytes_processed: int = 0
    bytes_returned: int = 0


def select_geojson_features(
    client: Any,
    *,
    bucket: str,
    key: str,
    query: str,
) -> tuple[list[dict[str, Any]], SelectStats]:
    """Execute an S3 Select query against a GeoJSON document."""
    response = client.select_object_content(
        Bucket=bucket,
        Key=key,
        Expression=query,
        ExpressionType="SQL",
        InputSerialization={"JSON": {"Type": "DOCUMENT"}},
        OutputSerialization={"JSON": {"RecordDelimiter": "\n"}},
    )

    payload = response["Payload"]
    features: list[dict[str, Any]] = []
    stats = SelectStats()
    buffer = b""

    for event in payload:
        records = event.get("Records")
        if records:
            buffer += records.get("Payload", b"")
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if line.strip():
                    features.append(json.loads(line))
        details = event.get("Stats", {}).get("Details")
        if details:
            stats = SelectStats(
                bytes_scanned=int(details.get("BytesScanned", 0)),
                bytes_processed=int(details.get("BytesProcessed", 0)),
                bytes_returned=int(details.get("BytesReturned", 0)),
            )

    if buffer.strip():
        features.append(json.loads(buffer))
    return features, stats
