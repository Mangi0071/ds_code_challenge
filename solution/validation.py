"""Data-quality validation for extracted GeoJSON."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class SchemaScore:
    score: float
    passed_checks: int
    failed_checks: int
    failures: list[str]


@dataclass(frozen=True)
class ReferenceComparison:
    matches: bool
    missing_indexes: set[str]
    extra_indexes: set[str]


def _coordinates_nonempty(coordinates: Any) -> bool:
    if not isinstance(coordinates, list) or not coordinates:
        return False
    if isinstance(coordinates[0], (int, float)):
        return len(coordinates) >= 2
    return any(_coordinates_nonempty(item) for item in coordinates)


def score_feature_collection(
    collection: dict[str, Any],
    *,
    h3_property: str,
    expected_resolution: int,
    is_valid_cell: Callable[[Any], bool],
    get_resolution: Callable[[str], int],
    collection_type: str = "FeatureCollection",
    feature_type: str = "Feature",
    geometry_type: str = "Polygon",
) -> SchemaScore:
    """Return a non-binary schema-conformance score from explicit checks.

    Each feature receives five equally weighted checks: GeoJSON feature type,
    properties object, Polygon geometry, non-empty coordinates, and a valid H3
    cell at the expected resolution. A collection-level type check is added too.
    """
    passed = 0
    failed = 0
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
        else:
            failed += 1
            failures.append(message)

    check(
        collection.get("type") == collection_type,
        f"collection.type must be {collection_type}",
    )
    features = collection.get("features")
    if not isinstance(features, list):
        check(False, "collection.features must be a list")
        total = passed + failed
        return SchemaScore(round(100 * passed / total, 2), passed, failed, failures)

    for idx, feature in enumerate(features):
        prefix = f"feature[{idx}]"
        check(
            feature.get("type") == feature_type,
            f"{prefix}.type must be {feature_type}",
        )

        properties = feature.get("properties")
        properties_ok = isinstance(properties, dict)
        check(properties_ok, f"{prefix}.properties must be an object")

        geometry = feature.get("geometry")
        geometry_ok = isinstance(geometry, dict)
        check(
            geometry_ok and geometry.get("type") == geometry_type,
            f"{prefix}.geometry.type must be {geometry_type}",
        )
        check(
            geometry_ok and _coordinates_nonempty(geometry.get("coordinates")),
            f"{prefix}.geometry.coordinates must be non-empty",
        )

        h3_value = properties.get(h3_property) if properties_ok else None
        h3_ok = bool(is_valid_cell(h3_value))
        if h3_ok:
            try:
                h3_ok = get_resolution(h3_value) == expected_resolution
            except (TypeError, ValueError):
                h3_ok = False
        check(
            h3_ok,
            f"{prefix}.properties.{h3_property} must be a valid H3 "
            f"resolution {expected_resolution} cell",
        )

    total = passed + failed
    score = round(100 * passed / total, 2) if total else 0.0
    return SchemaScore(score, passed, failed, failures)


def compare_feature_collections(
    extracted: dict[str, Any],
    reference: dict[str, Any],
    *,
    h3_property: str,
) -> ReferenceComparison:
    """Compare extracted and reference GeoJSON by H3 index, ignoring order."""

    def indexes(collection: dict[str, Any]) -> set[str]:
        values = set()
        for feature in collection.get("features", []):
            value = feature.get("properties", {}).get(h3_property)
            if value is not None:
                values.add(str(value))
        return values

    extracted_indexes = indexes(extracted)
    reference_indexes = indexes(reference)
    missing = reference_indexes - extracted_indexes
    extra = extracted_indexes - reference_indexes
    return ReferenceComparison(not missing and not extra, missing, extra)


def detect_h3_property(
    features: list[dict[str, Any]],
    *,
    is_valid_cell: Callable[[Any], bool],
) -> str:
    """Infer which GeoJSON property contains H3 cell indexes.

    The winning property must contain at least one valid H3 cell and all of its
    non-null sampled values must be valid H3 cells. Ambiguous inputs fail fast.
    """
    candidates: list[str] = []
    keys = {
        key
        for feature in features
        for key in feature.get("properties", {}).keys()
    }
    for key in sorted(keys):
        values = [
            feature.get("properties", {}).get(key)
            for feature in features
            if feature.get("properties", {}).get(key) is not None
        ]
        if values and all(is_valid_cell(value) for value in values):
            candidates.append(key)

    if len(candidates) > 1:
        named = [key for key in candidates if "h3" in key.lower()]
        if len(named) == 1:
            return named[0]
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one H3 property; found {candidates}")
    return candidates[0]


def detect_resolution_property(
    features: list[dict[str, Any]],
    *,
    expected_values: set[int],
) -> str:
    """Infer the property that stores integer H3 resolution values."""
    candidates: list[str] = []
    keys = {
        key
        for feature in features
        for key in feature.get("properties", {}).keys()
    }
    for key in sorted(keys):
        values = [
            feature.get("properties", {}).get(key)
            for feature in features
            if feature.get("properties", {}).get(key) is not None
        ]
        if not values:
            continue
        normalized: list[int] = []
        valid = True
        for value in values:
            try:
                number = int(value)
            except (TypeError, ValueError):
                valid = False
                break
            if number != value and not (
                isinstance(value, str) and str(number) == value.strip()
            ):
                valid = False
                break
            normalized.append(number)
        if valid and set(normalized).issubset(expected_values):
            candidates.append(key)

    if len(candidates) > 1:
        named = [
            key for key in candidates
            if key.lower() in {"resolution", "res", "h3_resolution"}
            or "resol" in key.lower()
        ]
        if len(named) == 1:
            return named[0]
    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one resolution property; found {candidates}"
        )
    return candidates[0]


def detect_resolution_property_from_h3(
    features: list[dict[str, Any]],
    *,
    h3_property: str,
    get_resolution: Callable[[str], int],
) -> str:
    """Infer resolution field by matching values to each feature's H3 resolution."""
    keys = {
        key
        for feature in features
        for key in feature.get("properties", {}).keys()
        if key != h3_property
    }
    candidates: list[str] = []
    h3_feature_count = sum(
        1
        for feature in features
        if feature.get("properties", {}).get(h3_property) is not None
    )
    for key in sorted(keys):
        matched = 0
        checked = 0
        for feature in features:
            properties = feature.get("properties", {})
            h3_value = properties.get(h3_property)
            value = properties.get(key)
            if h3_value is None or value is None:
                continue
            checked += 1
            try:
                if int(value) == int(get_resolution(str(h3_value))):
                    matched += 1
            except (TypeError, ValueError):
                break
        if checked == h3_feature_count and matched == checked:
            candidates.append(key)

    if len(candidates) > 1:
        named = [
            key for key in candidates
            if key.lower() in {"resolution", "res", "h3_resolution"}
            or "resol" in key.lower()
        ]
        if len(named) == 1:
            return named[0]
    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one property matching H3 resolution; found {candidates}"
        )
    return candidates[0]
