"""I/O helpers for AWS credentials and challenge datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AwsCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: str | None = None


def parse_aws_credentials(payload: dict[str, Any]) -> AwsCredentials:
    """Parse the public challenge credentials across common AWS key styles."""
    if isinstance(payload.get("Credentials"), dict):
        payload = payload["Credentials"]
    if isinstance(payload.get("s3"), dict):
        payload = payload["s3"]
    access_key = (
        payload.get("aws_access_key_id")
        or payload.get("AWS_ACCESS_KEY_ID")
        or payload.get("AccessKeyId")
        or payload.get("accessKeyId")
        or payload.get("access_key")
    )
    secret_key = (
        payload.get("aws_secret_access_key")
        or payload.get("AWS_SECRET_ACCESS_KEY")
        or payload.get("SecretAccessKey")
        or payload.get("secretAccessKey")
        or payload.get("secret_key")
    )
    session_token = (
        payload.get("aws_session_token")
        or payload.get("AWS_SESSION_TOKEN")
        or payload.get("SessionToken")
        or payload.get("sessionToken")
        or payload.get("Token")
    )
    if not access_key or not secret_key:
        raise ValueError(
            "Challenge credential JSON is missing an access key or secret key"
        )
    return AwsCredentials(
        str(access_key),
        str(secret_key),
        str(session_token) if session_token else None,
    )


def download_if_missing(client: Any, bucket: str, key: str, target: Path) -> bool:
    """Download one S3 object unless already cached locally.

    Returns True when a network download occurred and False on a cache hit.
    """
    target = Path(target)
    if target.exists() and target.stat().st_size > 0:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket, key, str(target))
    return True
