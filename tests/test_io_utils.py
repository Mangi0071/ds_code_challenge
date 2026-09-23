from solution.io_utils import parse_aws_credentials, download_if_missing


def test_parse_aws_credentials_accepts_lowercase_keys():
    creds = parse_aws_credentials(
        {"aws_access_key_id": "AKIA_TEST", "aws_secret_access_key": "SECRET"}
    )
    assert creds.access_key_id == "AKIA_TEST"
    assert creds.secret_access_key == "SECRET"


def test_parse_aws_credentials_accepts_aws_style_keys():
    creds = parse_aws_credentials(
        {"AccessKeyId": "AKIA_TEST", "SecretAccessKey": "SECRET"}
    )
    assert creds.access_key_id == "AKIA_TEST"
    assert creds.secret_access_key == "SECRET"


def test_download_if_missing_uses_cache(tmp_path):
    target = tmp_path / "file.csv"
    target.write_text("existing", encoding="utf-8")

    class Client:
        def download_file(self, *args, **kwargs):
            raise AssertionError("download_file should not be called for cached file")

    downloaded = download_if_missing(Client(), "bucket", "key", target)
    assert downloaded is False
    assert target.read_text(encoding="utf-8") == "existing"

def test_parse_aws_credentials_accepts_nested_challenge_s3_keys():
    creds = parse_aws_credentials(
        {"s3": {"access_key": "AKIA_TEST", "secret_key": "SECRET"}}
    )
    assert creds.access_key_id == "AKIA_TEST"
    assert creds.secret_access_key == "SECRET"
