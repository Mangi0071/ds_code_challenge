"""End-to-end runner for YearBeyond's requested Sections 0, 1 and 2."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from urllib.request import Request, urlopen

import boto3
import h3

from .config import load_yaml
from .csv_validation import compare_h3_csvs
from .io_utils import download_if_missing, parse_aws_credentials
from .s3_select import build_resolution_query, select_geojson_features
from .service_requests import process_service_requests
from .validation import (
    compare_feature_collections,
    detect_h3_property,
    detect_resolution_property_from_h3,
    score_feature_collection,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
LOG_DIR = ROOT / "logs"


def _configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "pipeline.log", mode="w", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
        force=True,
    )


def _fetch_credential_json(url: str) -> dict:
    request = Request(
        url, headers={"User-Agent": "yearbeyond-code-challenge/1.0"}
    )
    # The URL is a fixed HTTPS endpoint from the challenge configuration.
    with urlopen(request, timeout=30) as response:  # nosec B310
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("Credential endpoint did not return a JSON object")
    return payload


def _build_s3_client(pipeline_config: dict):
    aws_config = pipeline_config["aws"]
    credentials = parse_aws_credentials(
        _fetch_credential_json(aws_config["credentials_url"])
    )
    kwargs = {
        "service_name": "s3",
        "region_name": aws_config["region"],
        "aws_access_key_id": credentials.access_key_id,
        "aws_secret_access_key": credentials.secret_access_key,
    }
    if credentials.session_token:
        kwargs["aws_session_token"] = credentials.session_token
    return boto3.client(**kwargs)


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _write_geojson(path: Path, collection: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(collection, handle, separators=(",", ":"))


def _discover_source_fields(
    features: list[dict], schema_config: dict
) -> tuple[str, str]:
    expected = schema_config["expected"]

    configured_h3 = expected.get("h3_property", "auto")
    h3_property = (
        detect_h3_property(features, is_valid_cell=h3.is_valid_cell)
        if configured_h3 == "auto"
        else str(configured_h3)
    )

    configured_resolution = expected.get("resolution_property", "auto")
    resolution_property = (
        detect_resolution_property_from_h3(
            features, h3_property=h3_property, get_resolution=h3.get_resolution
        )
        if configured_resolution == "auto"
        else str(configured_resolution)
    )
    return h3_property, resolution_property


def main() -> None:
    _configure_logging()
    log = logging.getLogger(__name__)
    started = time.perf_counter()

    pipeline_config = load_yaml(CONFIG_DIR / "pipeline.yaml")
    schema_config = load_yaml(CONFIG_DIR / "geojson_schema.yaml")
    aws_config = pipeline_config["aws"]
    objects = pipeline_config["objects"]
    processing = pipeline_config["processing"]
    bucket = aws_config["bucket"]
    expected_resolution = int(schema_config["expected"]["h3_resolution"])

    log.info("Starting Sections 1 and 2 pipeline")
    client = _build_s3_client(pipeline_config)

    # SECTION 1: sample first so source field names are verified rather than assumed.
    sample_query = (
        "SELECT * FROM S3Object[*].features[*] AS f "
        f"LIMIT {int(processing['sample_features'])}"
    )
    sample_started = time.perf_counter()
    sample_features, sample_stats = select_geojson_features(
        client,
        bucket=bucket,
        key=objects["mixed_hex_geojson"],
        query=sample_query,
    )
    if not sample_features:
        raise RuntimeError("S3 Select sample returned no GeoJSON features")
    h3_property, resolution_property = _discover_source_fields(
        sample_features, schema_config
    )
    log.info(
        "Source discovery complete in %.2fs | h3_property=%s | "
        "resolution_property=%s | bytes_scanned=%s",
        time.perf_counter() - sample_started,
        h3_property,
        resolution_property,
        sample_stats.bytes_scanned,
    )

    sample_resolution_value = sample_features[0].get("properties", {}).get(
        resolution_property
    )
    select_query = build_resolution_query(
        resolution_property,
        expected_resolution,
        value_is_string=isinstance(sample_resolution_value, str),
    )

    extraction_started = time.perf_counter()
    extracted_features, select_stats = select_geojson_features(
        client,
        bucket=bucket,
        key=objects["mixed_hex_geojson"],
        query=select_query,
    )
    extracted_collection = {
        "type": schema_config["expected"]["collection_type"],
        "features": extracted_features,
    }
    extraction_seconds = time.perf_counter() - extraction_started
    log.info(
        "Section 1 extraction complete in %.2fs | features=%d | scanned=%d B | "
        "processed=%d B | returned=%d B",
        extraction_seconds,
        len(extracted_features),
        select_stats.bytes_scanned,
        select_stats.bytes_processed,
        select_stats.bytes_returned,
    )

    validation_started = time.perf_counter()
    schema_result = score_feature_collection(
        extracted_collection,
        h3_property=h3_property,
        expected_resolution=expected_resolution,
        is_valid_cell=h3.is_valid_cell,
        get_resolution=h3.get_resolution,
        collection_type=schema_config["expected"]["collection_type"],
        feature_type=schema_config["expected"]["feature_type"],
        geometry_type=schema_config["expected"]["geometry_type"],
    )
    schema_threshold = float(schema_config["conformance_threshold_percent"])
    log.info(
        "Section 1 schema conformance=%.2f%% | threshold=%.2f%% | "
        "failed_checks=%d | validation_time=%.2fs",
        schema_result.score,
        schema_threshold,
        schema_result.failed_checks,
        time.perf_counter() - validation_started,
    )
    if schema_result.score < schema_threshold:
        examples = "; ".join(schema_result.failures[:10])
        raise RuntimeError(
            f"Schema conformance {schema_result.score:.2f}% is below "
            f"{schema_threshold:.2f}%. Examples: {examples}"
        )

    extracted_path = PROCESSED_DIR / "city-hex-polygons-8-extracted.geojson"
    _write_geojson(extracted_path, extracted_collection)

    reference_hex_path = RAW_DIR / objects["reference_hex_geojson"]
    download_if_missing(
        client, bucket, objects["reference_hex_geojson"], reference_hex_path
    )
    reference_collection = _load_json(reference_hex_path)
    reference_result = compare_feature_collections(
        extracted_collection,
        reference_collection,
        h3_property=h3_property,
    )
    log.info(
        "Section 1 reference validation | missing=%d | extra=%d",
        len(reference_result.missing_indexes),
        len(reference_result.extra_indexes),
    )
    if not reference_result.matches:
        raise RuntimeError(
            "Extracted H3 set does not match city-hex-polygons-8.geojson: "
            f"missing={len(reference_result.missing_indexes)}, "
            f"extra={len(reference_result.extra_indexes)}"
        )

    city_h3_indexes = {
        str(feature["properties"][h3_property])
        for feature in extracted_features
        if feature.get("properties", {}).get(h3_property) is not None
    }

    # SECTION 2: download once, then process the large CSV in chunks.
    sr_path = RAW_DIR / objects["service_requests"]
    sr_reference_path = RAW_DIR / objects["service_requests_reference"]
    download_started = time.perf_counter()
    download_if_missing(client, bucket, objects["service_requests"], sr_path)
    download_if_missing(
        client, bucket, objects["service_requests_reference"], sr_reference_path
    )
    log.info(
        "Section 2 source downloads/cache checks complete in %.2fs",
        time.perf_counter() - download_started,
    )

    output_path = PROCESSED_DIR / "sr_with_h3.csv.gz"
    transform_started = time.perf_counter()
    join_metrics = process_service_requests(
        sr_path,
        output_path,
        city_h3_indexes=city_h3_indexes,
        latlng_to_cell=h3.latlng_to_cell,
        chunksize=int(processing["csv_chunk_size"]),
        max_join_failure_rate=float(processing["max_join_failure_rate"]),
    )
    log.info(
        "Section 2 transform complete in %.2fs | rows=%d | joined=%d | "
        "missing_coords=%d | invalid_coords=%d | join_failures=%d (%.4f%%)",
        time.perf_counter() - transform_started,
        join_metrics.total_rows,
        join_metrics.joined_rows,
        join_metrics.missing_coordinate_rows,
        join_metrics.invalid_coordinate_rows,
        join_metrics.join_failures,
        join_metrics.join_failure_rate * 100,
    )

    reference_started = time.perf_counter()
    csv_result = compare_h3_csvs(
        output_path,
        sr_reference_path,
        chunksize=int(processing["csv_chunk_size"]),
    )
    allowed_mismatch = float(processing["max_reference_mismatch_rate"])
    log.info(
        "Section 2 reference validation in %.2fs | compared=%d | "
        "mismatches=%d (%.6f%%) | threshold=%.6f%%",
        time.perf_counter() - reference_started,
        csv_result.total_rows,
        csv_result.mismatches,
        csv_result.mismatch_rate * 100,
        allowed_mismatch * 100,
    )
    if csv_result.mismatch_rate > allowed_mismatch:
        raise RuntimeError(
            f"Reference mismatch rate {csv_result.mismatch_rate:.6%} exceeds "
            f"threshold {allowed_mismatch:.6%}"
        )

    log.info(
        "SUCCESS: Sections 1 and 2 completed in %.2fs",
        time.perf_counter() - started,
    )


if __name__ == "__main__":
    main()
