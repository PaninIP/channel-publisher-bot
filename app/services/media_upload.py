from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from app.config import Settings

PHOTO_CONTENT_TYPES = {
    "image/jpeg": ("photo", ".jpg"),
    "image/png": ("photo", ".png"),
}
VIDEO_CONTENT_TYPES = {
    "video/mp4": ("video", ".mp4"),
}
SUPPORTED_CONTENT_TYPES = PHOTO_CONTENT_TYPES | VIDEO_CONTENT_TYPES


class MediaUploadValidationError(ValueError):
    pass


def classify_media(content_type: str) -> tuple[str, str]:
    normalized = content_type.split(";", maxsplit=1)[0].strip().lower()
    result = SUPPORTED_CONTENT_TYPES.get(normalized)
    if result is None:
        raise MediaUploadValidationError("Поддерживаются только JPEG, PNG и MP4.")
    return result


def maximum_file_size(
    *,
    media_type: str,
    settings: Settings,
) -> int:
    if media_type == "photo":
        return settings.media_photo_max_bytes
    if media_type == "video":
        return settings.media_video_max_bytes
    raise MediaUploadValidationError("Неизвестный тип вложения.")


def validate_file_signature(path: Path, content_type: str) -> None:
    with path.open("rb") as file:
        header = file.read(32)

    if content_type == "image/jpeg":
        valid = header.startswith(b"\xff\xd8\xff")
    elif content_type == "image/png":
        valid = header.startswith(b"\x89PNG\r\n\x1a\n")
    elif content_type == "video/mp4":
        valid = len(header) >= 12 and header[4:8] == b"ftyp"
    else:
        valid = False

    if not valid:
        raise MediaUploadValidationError(
            "Содержимое файла не соответствует заявленному MIME-type."
        )


def normalize_filename(filename: str, extension: str) -> str:
    clean = Path(filename.replace("\\", "/")).name.strip()
    clean = re.sub(r"[\x00-\x1f\x7f]", "", clean)
    stem = Path(clean).stem.strip(". ") or "media"
    maximum_stem_length = 255 - len(extension)
    return f"{stem[:maximum_stem_length]}{extension}"


def build_storage_key(
    *,
    owner_telegram_id: int,
    publication_id: int,
    extension: str,
) -> str:
    return (
        f"owners/{owner_telegram_id}/publications/{publication_id}/"
        f"{uuid4().hex}{extension}"
    )
