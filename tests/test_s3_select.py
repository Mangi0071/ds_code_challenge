from solution.s3_select import (
    build_resolution_query,
    parse_select_payload,
    quote_identifier,
)


def test_identifier_quoting_escapes_double_quotes():
    assert quote_identifier('h3"level') == '"h3""level"'


def test_resolution_query_filters_nested_geojson_features():
    query = build_resolution_query("resolution", 8)
    assert "FROM S3Object[*].features[*]" in query
    assert 'f.properties."resolution" = 8' in query


def test_payload_parser_handles_json_split_across_event_chunks():
    payload = [
        {"Records": {"Payload": b'{"type":"Feature","properties":{"a":1}}\n{"type":"Fe'}},
        {"Records": {"Payload": b'ature","properties":{"a":2}}\n'}},
        {"End": {}},
    ]

    records = list(parse_select_payload(payload))

    assert [r["properties"]["a"] for r in records] == [1, 2]


def test_select_geojson_features_calls_s3_select_and_collects_stats():
    from solution.s3_select import select_geojson_features

    class FakeClient:
        def __init__(self):
            self.kwargs = None

        def select_object_content(self, **kwargs):
            self.kwargs = kwargs
            return {
                "Payload": [
                    {"Records": {"Payload": b'{"type":"Feature","properties":{"x":1}}\n'}},
                    {
                        "Stats": {
                            "Details": {
                                "BytesScanned": 1000,
                                "BytesProcessed": 900,
                                "BytesReturned": 50,
                            }
                        }
                    },
                    {"End": {}},
                ]
            }

    client = FakeClient()
    features, stats = select_geojson_features(
        client,
        bucket="bucket",
        key="data.geojson",
        query="SELECT * FROM S3Object[*].features[*] f LIMIT 1",
    )

    assert len(features) == 1
    assert stats.bytes_scanned == 1000
    assert client.kwargs["ExpressionType"] == "SQL"
    assert client.kwargs["InputSerialization"] == {"JSON": {"Type": "DOCUMENT"}}
    assert client.kwargs["OutputSerialization"]["JSON"]["RecordDelimiter"] == "\n"


def test_resolution_query_can_compare_string_encoded_resolution():
    query = build_resolution_query("resolution", 8, value_is_string=True)
    assert 'f.properties."resolution" = \'8\'' in query
