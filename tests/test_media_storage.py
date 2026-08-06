from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import Settings
from app.services.media_storage import (
    LocalMediaStorage,
    MediaStorageError,
    S3MediaStorage,
)


@pytest.mark.asyncio
async def test_local_storage_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"telegram-media")
    destination = tmp_path / "download.bin"
    storage = LocalMediaStorage(str(tmp_path / "storage"))

    await storage.put_file(
        source_path=source,
        storage_key="owners/1/publications/2/file.bin",
        content_type="application/octet-stream",
    )
    await storage.download_to_path(
        storage_key="owners/1/publications/2/file.bin",
        destination_path=destination,
    )

    assert destination.read_bytes() == b"telegram-media"

    await storage.delete_file(storage_key="owners/1/publications/2/file.bin")
    with pytest.raises(MediaStorageError, match="отсутствует"):
        await storage.download_to_path(
            storage_key="owners/1/publications/2/file.bin",
            destination_path=destination,
        )


def test_local_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalMediaStorage(str(tmp_path / "storage"))

    with pytest.raises(MediaStorageError, match="Некорректный ключ"):
        storage._resolve_key("../secret.env")


def build_s3_storage() -> S3MediaStorage:
    settings = Settings(
        bot_token="test-token",
        media_storage_backend="s3",
        media_s3_endpoint="https://s3.eu-central-003.backblazeb2.com",
        media_s3_region="eu-central-003",
        media_s3_bucket="publisher-media",
        media_s3_key_id="key-id",
        media_s3_application_key="application-key",
    )
    return S3MediaStorage(settings)


def test_s3_storage_builds_path_style_url() -> None:
    storage = build_s3_storage()

    url, canonical_uri = storage._request_parts("owners/1/publications/2/my photo.jpg")

    assert url == (
        "https://s3.eu-central-003.backblazeb2.com/"
        "publisher-media/owners/1/publications/2/my%20photo.jpg"
    )
    assert canonical_uri.endswith("my%20photo.jpg")


def test_s3_signature_is_deterministic() -> None:
    storage = build_s3_storage()
    headers = storage._signed_headers(
        method="PUT",
        canonical_uri="/publisher-media/owners/1/file.jpg",
        payload_hash="0" * 64,
        content_type="image/jpeg",
        now=datetime(2026, 8, 6, 20, 0, tzinfo=UTC),
    )

    assert headers["X-Amz-Date"] == "20260806T200000Z"
    assert (
        "Credential=key-id/20260806/eu-central-003/s3/aws4_request"
        in headers["Authorization"]
    )
    assert (
        "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date"
        in headers["Authorization"]
    )
