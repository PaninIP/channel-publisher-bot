from pathlib import Path

import pytest

from app.config import Settings
from app.services.media_upload import (
    MediaUploadValidationError,
    build_storage_key,
    classify_media,
    maximum_file_size,
    normalize_filename,
    validate_file_signature,
)


def build_settings() -> Settings:
    return Settings(bot_token="test-token")


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("image/jpeg", ("photo", ".jpg")),
        ("image/png; charset=binary", ("photo", ".png")),
        ("video/mp4", ("video", ".mp4")),
    ],
)
def test_classify_supported_media(
    content_type: str,
    expected: tuple[str, str],
) -> None:
    assert classify_media(content_type) == expected


def test_classify_rejects_unknown_media() -> None:
    with pytest.raises(MediaUploadValidationError, match="JPEG, PNG и MP4"):
        classify_media("application/pdf")


@pytest.mark.parametrize(
    ("content_type", "header"),
    [
        ("image/jpeg", b"\xff\xd8\xff\xe0" + b"0" * 28),
        ("image/png", b"\x89PNG\r\n\x1a\n" + b"0" * 24),
        ("video/mp4", b"\x00\x00\x00\x18ftypisom" + b"0" * 20),
    ],
)
def test_validate_file_signature_accepts_supported_files(
    tmp_path: Path,
    content_type: str,
    header: bytes,
) -> None:
    path = tmp_path / "media"
    path.write_bytes(header)

    validate_file_signature(path, content_type)


def test_validate_file_signature_rejects_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "fake.jpg"
    path.write_bytes(b"not-a-photo")

    with pytest.raises(MediaUploadValidationError, match="MIME-type"):
        validate_file_signature(path, "image/jpeg")


def test_normalize_filename_removes_path_and_control_characters() -> None:
    assert (
        normalize_filename("C:\\fakepath/../bad\x00name.exe", ".png") == "badname.png"
    )


def test_storage_key_is_owner_and_publication_scoped() -> None:
    key = build_storage_key(
        owner_telegram_id=123,
        publication_id=456,
        extension=".jpg",
    )

    assert key.startswith("owners/123/publications/456/")
    assert key.endswith(".jpg")
    assert ".." not in key


def test_maximum_file_sizes_are_configurable() -> None:
    settings = build_settings()

    assert maximum_file_size(media_type="photo", settings=settings) == 10 * 1024 * 1024
    assert maximum_file_size(media_type="video", settings=settings) == 50 * 1024 * 1024
