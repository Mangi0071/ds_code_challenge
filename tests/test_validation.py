from solution.validation import (
    compare_feature_collections,
    score_feature_collection,
)


VALID_FEATURE = {
    "type": "Feature",
    "properties": {"h3_index": "88195da49bfffff"},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[18.4, -33.9], [18.5, -33.9], [18.5, -34.0], [18.4, -33.9]]],
    },
}


def fake_is_valid_cell(value):
    return isinstance(value, str) and value.startswith("88") and len(value) == 15


def fake_get_resolution(value):
    return 8 if fake_is_valid_cell(value) else -1


def test_schema_score_is_100_for_valid_feature_collection():
    collection = {"type": "FeatureCollection", "features": [VALID_FEATURE]}
    result = score_feature_collection(
        collection,
        h3_property="h3_index",
        expected_resolution=8,
        is_valid_cell=fake_is_valid_cell,
        get_resolution=fake_get_resolution,
    )
    assert result.score == 100.0
    assert result.failed_checks == 0


def test_schema_score_is_non_binary_and_reports_failures():
    broken = {
        "type": "Feature",
        "properties": {"h3_index": "bad"},
        "geometry": {"type": "Point", "coordinates": []},
    }
    collection = {"type": "FeatureCollection", "features": [VALID_FEATURE, broken]}
    result = score_feature_collection(
        collection,
        h3_property="h3_index",
        expected_resolution=8,
        is_valid_cell=fake_is_valid_cell,
        get_resolution=fake_get_resolution,
    )
    assert 0.0 < result.score < 100.0
    assert result.failed_checks > 0
    assert result.failures


def test_reference_comparison_uses_h3_sets_not_feature_order():
    f1 = VALID_FEATURE
    f2 = {
        **VALID_FEATURE,
        "properties": {"h3_index": "88195da49afffff"},
    }
    extracted = {"type": "FeatureCollection", "features": [f1, f2]}
    reference = {"type": "FeatureCollection", "features": [f2, f1]}

    result = compare_feature_collections(extracted, reference, h3_property="h3_index")

    assert result.matches
    assert result.missing_indexes == set()
    assert result.extra_indexes == set()


def test_detects_h3_property_from_feature_values():
    from solution.validation import detect_h3_property

    features = [
        {"properties": {"name": "A", "hex_code": "88195da49bfffff", "resolution": 8}},
        {"properties": {"name": "B", "hex_code": "88195da49afffff", "resolution": 8}},
    ]
    prop = detect_h3_property(features, is_valid_cell=fake_is_valid_cell)
    assert prop == "hex_code"


def test_detects_numeric_resolution_property_when_present():
    from solution.validation import detect_resolution_property

    features = [
        {"properties": {"hex_code": "88195da49bfffff", "resolution": 8}},
        {"properties": {"hex_code": "89195da49b3ffff", "resolution": 9}},
        {"properties": {"hex_code": "8a195da49b37fff", "resolution": 10}},
    ]
    assert detect_resolution_property(features, expected_values={8, 9, 10}) == "resolution"


def test_detect_resolution_property_matches_h3_resolution_per_feature():
    from solution.validation import detect_resolution_property_from_h3

    features = [
        {"properties": {"hex_code": "88195da49bfffff", "resolution": 8, "other_small_int": 8}},
        {"properties": {"hex_code": "89195da49b3ffff", "resolution": 9, "other_small_int": 8}},
    ]

    def fake_resolution(value):
        return {"88": 8, "89": 9}[value[:2]]

    assert (
        detect_resolution_property_from_h3(
            features,
            h3_property="hex_code",
            get_resolution=fake_resolution,
        )
        == "resolution"
    )
