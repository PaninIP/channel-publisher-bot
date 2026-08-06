import json
import logging
import os
import tempfile
from datetime import UTC, datetime, timedelta, timezone as fixed_timezone, tzinfo
from pathlib import Path
from urllib.parse import unquote
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import (
    FileResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.config import Settings, get_settings
from app.database.models import (
    Publication,
    PublicationMedia,
    PublicationStatus,
)
from app.database.repositories.channel_repository import (
    ChannelRepository,
)
from app.database.repositories.publication_media_repository import (
    PublicationMediaConflictError,
    PublicationMediaRepository,
    PublicationMediaValidationError,
)
from app.database.repositories.publication_repository import (
    PublicationRepository,
)
from app.database.session import SessionFactory
from app.services.content_plan_editor import (
    ContentPlanEditorValidationError,
    normalize_publication_text,
    parse_scheduled_local,
)
from app.services.media_storage import (
    MediaStorageError,
    get_media_storage,
    get_media_storage_for_backend,
)
from app.services.media_upload import (
    MediaUploadValidationError,
    build_storage_key,
    classify_media,
    maximum_file_size,
    normalize_filename,
    validate_file_signature,
)
from app.services.telegram_entities import (
    TelegramEntityValidationError,
    dump_telegram_entities,
    load_telegram_entities,
    normalize_telegram_entities,
)
from app.services.telegram_webapp import (
    TelegramWebAppAuthError,
    validate_telegram_init_data,
)

WEBAPP_DIRECTORY = Path(__file__).resolve().parent.parent / "webapp"
logger = logging.getLogger(__name__)

CONTENT_TYPE_LABELS = {
    "text": "Текст",
    "photo": "Фотография",
    "video": "Видео",
    "album": "Альбом",
}

MEDIA_CONTENT_TYPES = {
    "photo": "image/jpeg",
    "video": "video/mp4",
}


class PublicationEntityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "bold",
        "italic",
        "underline",
        "strikethrough",
        "spoiler",
        "blockquote",
        "expandable_blockquote",
        "code",
        "pre",
        "text_link",
    ]
    offset: int = Field(ge=0)
    length: int = Field(gt=0)
    url: str | None = Field(default=None, max_length=2048)
    language: str | None = Field(default=None, max_length=64)


class PublicationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_id: int = Field(gt=0)
    expected_version: int = Field(ge=1)
    text: str | None = Field(
        default=None,
        max_length=4096,
    )
    text_entities: list[PublicationEntityRequest] = Field(
        default_factory=list,
        max_length=100,
    )
    scheduled_local: str = Field(
        min_length=16,
        max_length=32,
    )
    timezone: str = Field(
        default="",
        max_length=64,
    )
    timezone_offset_minutes: int | None = Field(
        default=None,
        ge=-(14 * 60),
        le=14 * 60,
    )
    show_caption_above_media: bool = False


class MediaOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    media_ids: list[int] = Field(min_length=1, max_length=10)


class MediaOptionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    media_id: int | None = Field(default=None, gt=0)
    has_spoiler: bool | None = None
    show_caption_above_media: bool | None = None


app = FastAPI(
    title="Channel Publisher Mini App",
    docs_url=None,
    redoc_url=None,
)

app.mount(
    "/static",
    StaticFiles(
        directory=WEBAPP_DIRECTORY,
    ),
    name="static",
)


def authenticate_telegram_user(
    init_data: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    try:
        return validate_telegram_init_data(
            init_data,
            bot_token=(settings.bot_token.get_secret_value()),
            max_age_seconds=(settings.mini_app_auth_max_age_seconds),
        )
    except TelegramWebAppAuthError as error:
        raise HTTPException(
            status_code=(status.HTTP_401_UNAUTHORIZED),
            detail=str(error),
        ) from error


def format_timezone_offset(timezone_offset_minutes: int) -> str:
    sign = "+" if timezone_offset_minutes >= 0 else "-"
    absolute_minutes = abs(timezone_offset_minutes)
    hours, minutes = divmod(absolute_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def get_requested_timezone(
    timezone_name: str | None,
    timezone_offset_minutes: int | None,
    *,
    settings: Settings,
) -> tuple[tzinfo, str]:
    requested_timezone = (timezone_name or "").strip()

    if requested_timezone:
        try:
            return ZoneInfo(requested_timezone), requested_timezone
        except ZoneInfoNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Устройство передало неизвестный часовой пояс.",
            ) from error

    if timezone_offset_minutes is None:
        fallback_timezone = settings.app_timezone.strip()

        try:
            return ZoneInfo(fallback_timezone), fallback_timezone
        except ZoneInfoNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="На сервере некорректно настроен APP_TIMEZONE.",
            ) from error

    if not -(14 * 60) <= timezone_offset_minutes <= 14 * 60:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Устройство передало некорректный часовой пояс.",
        )

    timezone_label = format_timezone_offset(timezone_offset_minutes)
    return (
        fixed_timezone(timedelta(minutes=timezone_offset_minutes)),
        timezone_label,
    )


def get_month_bounds_utc(
    month_value: str,
    *,
    timezone: tzinfo,
) -> tuple[datetime, datetime]:
    try:
        year_text, month_text = month_value.split("-", maxsplit=1)
        year = int(year_text)
        month = int(month_text)

        if not 1 <= month <= 12:
            raise ValueError
    except ValueError as error:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_ENTITY),
            detail=("Месяц должен иметь формат YYYY-MM."),
        ) from error

    local_start = datetime(
        year,
        month,
        1,
        tzinfo=timezone,
    )

    if month == 12:
        local_end = datetime(
            year + 1,
            1,
            1,
            tzinfo=timezone,
        )
    else:
        local_end = datetime(
            year,
            month + 1,
            1,
            tzinfo=timezone,
        )

    return (
        local_start.astimezone(UTC).replace(tzinfo=None),
        local_end.astimezone(UTC).replace(tzinfo=None),
    )


def to_local_datetime(
    value: datetime,
    *,
    timezone: tzinfo,
) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(timezone)


def build_preview(
    text: str | None,
    *,
    limit: int = 180,
) -> str:
    if not text:
        return "Без текста"

    preview = " ".join(text.strip().split())

    if len(preview) > limit:
        return f"{preview[: limit - 1]}…"

    return preview


def serialize_media_item(
    media: PublicationMedia,
    *,
    publication_id: int,
) -> dict[str, object]:
    return {
        "id": media.id,
        "media_type": media.media_type,
        "content_type": media.content_type,
        "original_filename": media.original_filename
        or ("Фотография" if media.media_type == "photo" else "Видео"),
        "file_size": media.file_size,
        "position": media.position,
        "has_spoiler": media.has_spoiler,
        "preview_url": (f"/api/publications/{publication_id}/media/{media.id}/content"),
        "storage_backend": media.storage_backend,
    }


def media_mutation_http_error(error: Exception) -> HTTPException:
    if isinstance(error, PublicationMediaConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        )
    if isinstance(
        error,
        (PublicationMediaValidationError, MediaUploadValidationError),
    ):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        )
    if isinstance(error, MediaStorageError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Не удалось изменить вложения.",
    )


async def receive_media_upload(
    request: Request,
    *,
    maximum_bytes: int,
) -> tuple[Path, int]:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError as error:
            raise MediaUploadValidationError(
                "Некорректный размер загружаемого файла."
            ) from error
        if declared_size > maximum_bytes:
            raise MediaUploadValidationError(
                f"Файл превышает лимит {maximum_bytes // (1024 * 1024)} МБ."
            )

    temporary = tempfile.NamedTemporaryFile(
        prefix="miniapp-upload-",
        delete=False,
    )
    path = Path(temporary.name)
    total = 0

    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > maximum_bytes:
                raise MediaUploadValidationError(
                    f"Файл превышает лимит {maximum_bytes // (1024 * 1024)} МБ."
                )
            temporary.write(chunk)
    except Exception:
        temporary.close()
        path.unlink(missing_ok=True)
        raise
    finally:
        if not temporary.closed:
            temporary.close()

    if total == 0:
        path.unlink(missing_ok=True)
        raise MediaUploadValidationError("Получен пустой файл.")
    return path, total


async def delete_storage_object_safely(
    *,
    settings: Settings,
    media: PublicationMedia,
) -> None:
    if not media.storage_key or media.storage_backend == "telegram":
        return
    try:
        storage = get_media_storage_for_backend(
            settings,
            media.storage_backend,
        )
        await storage.delete_file(storage_key=media.storage_key)
    except MediaStorageError:
        logger.exception(
            "Failed to delete orphan media object %s",
            media.storage_key,
        )


async def get_owned_scheduled_publication(
    *,
    publication_id: int,
    owner_telegram_id: int,
) -> Publication:
    async with SessionFactory() as session:
        repository = PublicationRepository(session)
        publication = await repository.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=(owner_telegram_id),
        )

        if publication is None:
            raise HTTPException(
                status_code=(status.HTTP_404_NOT_FOUND),
                detail=("Публикация не найдена."),
            )

        if publication.status != PublicationStatus.SCHEDULED.value:
            raise HTTPException(
                status_code=(status.HTTP_409_CONFLICT),
                detail=("Редактировать можно только запланированную публикацию."),
            )

        session.expunge(publication)
        return publication


@app.get(
    "/",
    include_in_schema=False,
)
async def index() -> FileResponse:
    return FileResponse(
        WEBAPP_DIRECTORY / "index.html",
    )


@app.get(
    "/plan",
    include_in_schema=False,
)
async def content_plan_page() -> FileResponse:
    return FileResponse(
        WEBAPP_DIRECTORY / "content-plan.html",
    )


@app.get(
    "/health",
    include_in_schema=False,
)
async def health() -> dict[str, str]:
    try:
        async with SessionFactory() as session:
            await session.execute(select(Publication.id).limit(1))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="База данных недоступна.",
        ) from error

    try:
        storage = get_media_storage(get_settings())
    except MediaStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Хранилище медиа настроено некорректно.",
        ) from error

    return {
        "status": "ok",
        "database": "ok",
        "media_storage": storage.backend_name,
    }


@app.get("/api/content-plan")
async def get_content_plan(
    month: str = Query(
        pattern=r"^\d{4}-\d{2}$",
    ),
    timezone: str | None = Query(
        default=None,
        max_length=64,
    ),
    timezone_offset_minutes: int | None = Query(
        default=None,
        ge=-(14 * 60),
        le=14 * 60,
    ),
    telegram_init_data: str = Header(
        alias="X-Telegram-Init-Data",
    ),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(
        telegram_init_data,
        settings=settings,
    )
    requested_timezone, requested_timezone_name = get_requested_timezone(
        timezone,
        timezone_offset_minutes,
        settings=settings,
    )
    utc_start, utc_end = get_month_bounds_utc(
        month,
        timezone=requested_timezone,
    )
    owner_telegram_id = int(user["id"])

    async with SessionFactory() as session:
        publication_repository = PublicationRepository(session)
        channel_repository = ChannelRepository(session)

        publications = await publication_repository.list_scheduled_for_period(
            owner_telegram_id=(owner_telegram_id),
            starts_at_utc=utc_start,
            ends_at_utc=utc_end,
            limit=500,
        )

        channels = {
            channel.id: channel
            for channel in await channel_repository.list_by_owner(owner_telegram_id)
        }

    items: list[dict[str, object]] = []

    for publication in publications:
        if publication.scheduled_at is None:
            continue

        scheduled_local = to_local_datetime(
            publication.scheduled_at,
            timezone=requested_timezone,
        )
        channel = channels.get(publication.channel_id)

        items.append(
            {
                "id": publication.id,
                "day": (scheduled_local.strftime("%Y-%m-%d")),
                "time": (scheduled_local.strftime("%H:%M")),
                "scheduled_at": (scheduled_local.isoformat()),
                "channel_title": (
                    channel.title if channel is not None else "Удалённый канал"
                ),
                "content_type": (publication.content_type),
                "content_type_label": (
                    CONTENT_TYPE_LABELS.get(
                        publication.content_type,
                        publication.content_type,
                    )
                ),
                "preview": build_preview(publication.text),
                "has_media": publication.content_type != "text",
            }
        )

    return {
        "month": month,
        "timezone": requested_timezone_name,
        "items": items,
    }


@app.get("/api/publications/{publication_id}")
async def get_publication_details(
    publication_id: int,
    timezone: str | None = Query(
        default=None,
        max_length=64,
    ),
    timezone_offset_minutes: int | None = Query(
        default=None,
        ge=-(14 * 60),
        le=14 * 60,
    ),
    telegram_init_data: str = Header(
        alias="X-Telegram-Init-Data",
    ),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(
        telegram_init_data,
        settings=settings,
    )
    requested_timezone, requested_timezone_name = get_requested_timezone(
        timezone,
        timezone_offset_minutes,
        settings=settings,
    )
    owner_telegram_id = int(user["id"])

    async with SessionFactory() as session:
        publication_repository = PublicationRepository(session)
        media_repository = PublicationMediaRepository(session)
        channel_repository = ChannelRepository(session)

        publication = await publication_repository.get_by_id(
            publication_id=(publication_id),
            owner_telegram_id=(owner_telegram_id),
        )

        if publication is None:
            raise HTTPException(
                status_code=(status.HTTP_404_NOT_FOUND),
                detail="Публикация не найдена.",
            )

        if publication.status != PublicationStatus.SCHEDULED.value:
            raise HTTPException(
                status_code=(status.HTTP_409_CONFLICT),
                detail=("Редактировать можно только запланированную публикацию."),
            )

        channels = await channel_repository.list_by_owner(owner_telegram_id)
        media_items = await media_repository.list_by_publication(
            publication_id=publication.id,
            owner_telegram_id=owner_telegram_id,
        )

    if publication.scheduled_at is None:
        raise HTTPException(
            status_code=(status.HTTP_409_CONFLICT),
            detail=("У публикации отсутствует дата отправки."),
        )

    scheduled_local = to_local_datetime(
        publication.scheduled_at,
        timezone=requested_timezone,
    )

    return {
        "id": publication.id,
        "channel_id": publication.channel_id,
        "channels": [
            {
                "id": channel.id,
                "title": channel.title,
            }
            for channel in channels
        ],
        "content_type": (publication.content_type),
        "content_type_label": (
            CONTENT_TYPE_LABELS.get(
                publication.content_type,
                publication.content_type,
            )
        ),
        "text": publication.text or "",
        "text_entities": load_telegram_entities(publication.text_entities_json),
        "version": publication.version,
        "scheduled_local": (scheduled_local.strftime("%Y-%m-%dT%H:%M")),
        "timezone": requested_timezone_name,
        "has_media": bool(media_items),
        "media": [
            serialize_media_item(item, publication_id=publication.id)
            for item in media_items
        ],
        "media_max_items": settings.media_max_items,
        "media_photo_max_bytes": settings.media_photo_max_bytes,
        "media_video_max_bytes": settings.media_video_max_bytes,
        "show_caption_above_media": publication.show_caption_above_media,
    }


@app.patch("/api/publications/{publication_id}")
async def update_publication(
    publication_id: int,
    payload: PublicationUpdateRequest,
    telegram_init_data: str = Header(
        alias="X-Telegram-Init-Data",
    ),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(
        telegram_init_data,
        settings=settings,
    )
    owner_telegram_id = int(user["id"])

    async with SessionFactory() as session:
        publication_repository = PublicationRepository(session)
        media_repository = PublicationMediaRepository(session)
        channel_repository = ChannelRepository(session)

        publication = await publication_repository.get_by_id(
            publication_id=(publication_id),
            owner_telegram_id=(owner_telegram_id),
        )

        if publication is None:
            raise HTTPException(
                status_code=(status.HTTP_404_NOT_FOUND),
                detail="Публикация не найдена.",
            )

        if publication.status != PublicationStatus.SCHEDULED.value:
            raise HTTPException(
                status_code=(status.HTTP_409_CONFLICT),
                detail=("Редактировать можно только запланированную публикацию."),
            )

        channel = await channel_repository.get_by_id(
            channel_id=payload.channel_id,
            owner_telegram_id=(owner_telegram_id),
        )

        if channel is None:
            raise HTTPException(
                status_code=(status.HTTP_422_UNPROCESSABLE_ENTITY),
                detail=("Выбранный канал недоступен."),
            )

        try:
            normalized_text = normalize_publication_text(
                payload.text,
                content_type=(publication.content_type),
            )
            normalized_entities = normalize_telegram_entities(
                normalized_text or "",
                [
                    entity.model_dump(exclude_none=True)
                    for entity in payload.text_entities
                ],
            )
            entities_json = dump_telegram_entities(normalized_entities)
            scheduled_at_utc = parse_scheduled_local(
                payload.scheduled_local,
                timezone_name=payload.timezone,
                timezone_offset_minutes=(payload.timezone_offset_minutes),
            )
        except (
            ContentPlanEditorValidationError,
            TelegramEntityValidationError,
        ) as error:
            raise HTTPException(
                status_code=(status.HTTP_422_UNPROCESSABLE_ENTITY),
                detail=str(error),
            ) from error

        media_items = await media_repository.list_by_publication(
            publication_id=publication.id,
            owner_telegram_id=owner_telegram_id,
        )

        next_version = await publication_repository.update_scheduled(
            publication,
            channel_id=channel.id,
            text=normalized_text,
            text_entities_json=entities_json,
            scheduled_at_utc=(scheduled_at_utc),
            expected_version=payload.expected_version,
            show_caption_above_media=payload.show_caption_above_media,
            media_items=media_items,
        )

        if next_version is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Публикация уже изменилась в другом окне, отправляется, "
                    "была отменена или больше недоступна. Обновите редактор."
                ),
            )

    return {
        "status": "updated",
        "publication_id": publication_id,
        "version": next_version,
    }


@app.get("/api/publications/{publication_id}/versions")
async def get_publication_versions(
    publication_id: int,
    timezone: str | None = Query(default=None, max_length=64),
    timezone_offset_minutes: int | None = Query(
        default=None,
        ge=-(14 * 60),
        le=14 * 60,
    ),
    telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(
        telegram_init_data,
        settings=settings,
    )
    requested_timezone, _ = get_requested_timezone(
        timezone,
        timezone_offset_minutes,
        settings=settings,
    )
    owner_telegram_id = int(user["id"])

    async with SessionFactory() as session:
        repository = PublicationRepository(session)
        publication = await repository.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )

        if publication is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Публикация не найдена.",
            )

        if publication.status != PublicationStatus.SCHEDULED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="История доступна только для запланированной публикации.",
            )

        versions = await repository.list_versions(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )

    def serialize_scheduled(value: datetime | None) -> str | None:
        if value is None:
            return None
        return to_local_datetime(
            value,
            timezone=requested_timezone,
        ).strftime("%Y-%m-%dT%H:%M")

    items: list[dict[str, object]] = [
        {
            "version": publication.version,
            "is_current": True,
            "channel_id": publication.channel_id,
            "text": publication.text or "",
            "text_entities": load_telegram_entities(publication.text_entities_json),
            "scheduled_local": serialize_scheduled(publication.scheduled_at),
            "created_at": to_local_datetime(
                publication.updated_at,
                timezone=requested_timezone,
            ).isoformat(),
        }
    ]

    for version in versions:
        try:
            snapshot = json.loads(version.snapshot_json)
        except (json.JSONDecodeError, TypeError):
            continue

        scheduled_value = snapshot.get("scheduled_at")
        scheduled_at = (
            datetime.fromisoformat(scheduled_value)
            if isinstance(scheduled_value, str) and scheduled_value
            else None
        )

        items.append(
            {
                "version": version.version,
                "is_current": False,
                "channel_id": snapshot.get("channel_id"),
                "text": snapshot.get("text") or "",
                "text_entities": load_telegram_entities(
                    snapshot.get("text_entities_json")
                ),
                "scheduled_local": serialize_scheduled(scheduled_at),
                "created_at": to_local_datetime(
                    version.created_at,
                    timezone=requested_timezone,
                ).isoformat(),
            }
        )

    return {"items": items}


async def store_uploaded_media(
    *,
    request: Request,
    publication_id: int,
    owner_telegram_id: int,
    expected_version: int,
    encoded_filename: str,
    replace_media_id: int | None,
    settings: Settings,
) -> dict[str, object]:
    content_type = (
        request.headers.get("content-type", "")
        .split(";", maxsplit=1)[0]
        .strip()
        .lower()
    )
    media_type, extension = classify_media(content_type)
    maximum_bytes = maximum_file_size(
        media_type=media_type,
        settings=settings,
    )
    filename = normalize_filename(unquote(encoded_filename), extension)
    temporary_path, file_size = await receive_media_upload(
        request,
        maximum_bytes=maximum_bytes,
    )
    storage = get_media_storage(settings)
    storage_key = build_storage_key(
        owner_telegram_id=owner_telegram_id,
        publication_id=publication_id,
        extension=extension,
    )
    uploaded = False

    try:
        validate_file_signature(temporary_path, content_type)
        await storage.put_file(
            source_path=temporary_path,
            storage_key=storage_key,
            content_type=content_type,
        )
        uploaded = True

        async with SessionFactory() as session:
            repository = PublicationMediaRepository(session)
            if replace_media_id is None:
                result = await repository.add_uploaded(
                    publication_id=publication_id,
                    owner_telegram_id=owner_telegram_id,
                    expected_version=expected_version,
                    media_type=media_type,
                    storage_backend=storage.backend_name,
                    storage_key=storage_key,
                    original_filename=filename,
                    content_type=content_type,
                    file_size=file_size,
                    max_items=settings.media_max_items,
                )
                previous = None
            else:
                result, previous = await repository.replace_uploaded(
                    publication_id=publication_id,
                    media_id=replace_media_id,
                    owner_telegram_id=owner_telegram_id,
                    expected_version=expected_version,
                    media_type=media_type,
                    storage_backend=storage.backend_name,
                    storage_key=storage_key,
                    original_filename=filename,
                    content_type=content_type,
                    file_size=file_size,
                )

        if previous is not None:
            await delete_storage_object_safely(
                settings=settings,
                media=previous,
            )
        return {
            "status": "updated",
            "version": result.version,
            "content_type": result.content_type,
            "show_caption_above_media": result.show_caption_above_media,
            "media": [
                serialize_media_item(item, publication_id=publication_id)
                for item in result.media
            ],
        }
    except Exception:
        if uploaded:
            try:
                await storage.delete_file(storage_key=storage_key)
            except MediaStorageError:
                logger.exception(
                    "Failed to delete rejected upload %s",
                    storage_key,
                )
        raise
    finally:
        temporary_path.unlink(missing_ok=True)


@app.post("/api/publications/{publication_id}/media")
async def upload_publication_media(
    publication_id: int,
    request: Request,
    file_name: str = Header(alias="X-File-Name", max_length=4096),
    expected_version: int = Header(alias="X-Expected-Version", ge=1),
    telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(telegram_init_data, settings=settings)
    try:
        return await store_uploaded_media(
            request=request,
            publication_id=publication_id,
            owner_telegram_id=int(user["id"]),
            expected_version=expected_version,
            encoded_filename=file_name,
            replace_media_id=None,
            settings=settings,
        )
    except Exception as error:
        if isinstance(
            error,
            (
                PublicationMediaConflictError,
                PublicationMediaValidationError,
                MediaUploadValidationError,
                MediaStorageError,
            ),
        ):
            raise media_mutation_http_error(error) from error
        raise


@app.put("/api/publications/{publication_id}/media/{media_id}")
async def replace_publication_media(
    publication_id: int,
    media_id: int,
    request: Request,
    file_name: str = Header(alias="X-File-Name", max_length=4096),
    expected_version: int = Header(alias="X-Expected-Version", ge=1),
    telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(telegram_init_data, settings=settings)
    try:
        return await store_uploaded_media(
            request=request,
            publication_id=publication_id,
            owner_telegram_id=int(user["id"]),
            expected_version=expected_version,
            encoded_filename=file_name,
            replace_media_id=media_id,
            settings=settings,
        )
    except Exception as error:
        if isinstance(
            error,
            (
                PublicationMediaConflictError,
                PublicationMediaValidationError,
                MediaUploadValidationError,
                MediaStorageError,
            ),
        ):
            raise media_mutation_http_error(error) from error
        raise


@app.delete("/api/publications/{publication_id}/media/{media_id}")
async def delete_publication_media(
    publication_id: int,
    media_id: int,
    expected_version: int = Query(ge=1),
    telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(telegram_init_data, settings=settings)
    try:
        async with SessionFactory() as session:
            repository = PublicationMediaRepository(session)
            result = await repository.remove(
                publication_id=publication_id,
                media_id=media_id,
                owner_telegram_id=int(user["id"]),
                expected_version=expected_version,
            )
        await delete_storage_object_safely(
            settings=settings,
            media=result.removed,
        )
    except (PublicationMediaConflictError, PublicationMediaValidationError) as error:
        raise media_mutation_http_error(error) from error

    return {
        "status": "deleted",
        "version": result.version,
        "content_type": result.content_type,
        "show_caption_above_media": result.show_caption_above_media,
        "media": [
            serialize_media_item(item, publication_id=publication_id)
            for item in result.media
        ],
    }


@app.patch("/api/publications/{publication_id}/media/order")
async def reorder_publication_media(
    publication_id: int,
    payload: MediaOrderRequest,
    telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(telegram_init_data, settings=settings)
    try:
        async with SessionFactory() as session:
            repository = PublicationMediaRepository(session)
            result = await repository.reorder(
                publication_id=publication_id,
                owner_telegram_id=int(user["id"]),
                expected_version=payload.expected_version,
                media_ids=payload.media_ids,
            )
    except (PublicationMediaConflictError, PublicationMediaValidationError) as error:
        raise media_mutation_http_error(error) from error

    return {
        "status": "reordered",
        "version": result.version,
        "content_type": result.content_type,
        "show_caption_above_media": result.show_caption_above_media,
        "media": [
            serialize_media_item(item, publication_id=publication_id)
            for item in result.media
        ],
    }


@app.patch("/api/publications/{publication_id}/media/options")
async def update_publication_media_options(
    publication_id: int,
    payload: MediaOptionsRequest,
    telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(telegram_init_data, settings=settings)
    if payload.show_caption_above_media is None and (
        payload.media_id is None or payload.has_spoiler is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Не переданы настройки для изменения.",
        )
    try:
        async with SessionFactory() as session:
            repository = PublicationMediaRepository(session)
            result = await repository.set_options(
                publication_id=publication_id,
                owner_telegram_id=int(user["id"]),
                expected_version=payload.expected_version,
                media_id=payload.media_id,
                has_spoiler=payload.has_spoiler,
                show_caption_above_media=payload.show_caption_above_media,
            )
    except (PublicationMediaConflictError, PublicationMediaValidationError) as error:
        raise media_mutation_http_error(error) from error

    return {
        "status": "updated",
        "version": result.version,
        "content_type": result.content_type,
        "show_caption_above_media": result.show_caption_above_media,
        "media": [
            serialize_media_item(item, publication_id=publication_id)
            for item in result.media
        ],
    }


async def build_media_file_response(
    *,
    media: PublicationMedia,
    settings: Settings,
) -> Response:
    temporary = tempfile.NamedTemporaryFile(
        prefix=f"media-preview-{media.id}-",
        suffix=Path(media.original_filename or "").suffix,
        delete=False,
    )
    temporary.close()
    temporary_path = Path(temporary.name)

    try:
        if media.storage_backend == "telegram":
            if not media.telegram_file_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Telegram file_id отсутствует.",
                )
            bot = Bot(token=settings.bot_token.get_secret_value())
            try:
                telegram_file = await bot.get_file(media.telegram_file_id)
                if not telegram_file.file_path:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Telegram не вернул путь к вложению.",
                    )
                await bot.download_file(
                    telegram_file.file_path,
                    destination=temporary_path,
                )
            except TelegramAPIError as error:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Не удалось получить вложение из Telegram.",
                ) from error
            finally:
                await bot.session.close()
        else:
            if not media.storage_key:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Файл вложения отсутствует.",
                )
            storage = get_media_storage_for_backend(
                settings,
                media.storage_backend,
            )
            await storage.download_to_path(
                storage_key=media.storage_key,
                destination_path=temporary_path,
            )
    except MediaStorageError as error:
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    response_kwargs: dict[str, object] = {
        "media_type": media.content_type
        or MEDIA_CONTENT_TYPES.get(
            media.media_type,
            "application/octet-stream",
        ),
        "headers": {"Cache-Control": "private, max-age=60"},
        "background": BackgroundTask(os.unlink, temporary_path),
    }
    if media.original_filename:
        response_kwargs["filename"] = media.original_filename
    return FileResponse(temporary_path, **response_kwargs)


@app.get("/api/publications/{publication_id}/media/{media_id}/content")
async def get_publication_media_content(
    publication_id: int,
    media_id: int,
    telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> Response:
    settings = get_settings()
    user = authenticate_telegram_user(telegram_init_data, settings=settings)
    async with SessionFactory() as session:
        repository = PublicationMediaRepository(session)
        media = await repository.get_by_id(
            publication_id=publication_id,
            media_id=media_id,
            owner_telegram_id=int(user["id"]),
        )
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Вложение не найдено.",
        )
    return await build_media_file_response(media=media, settings=settings)


@app.get("/api/publications/{publication_id}/media")
async def get_publication_media(
    publication_id: int,
    telegram_init_data: str = Header(alias="X-Telegram-Init-Data"),
) -> Response:
    settings = get_settings()
    user = authenticate_telegram_user(telegram_init_data, settings=settings)
    async with SessionFactory() as session:
        repository = PublicationMediaRepository(session)
        items = await repository.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=int(user["id"]),
        )
    if not items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="У публикации нет вложений.",
        )
    return await build_media_file_response(media=items[0], settings=settings)
