import json
from datetime import UTC, datetime, timedelta, timezone as fixed_timezone, tzinfo
from io import BytesIO
from pathlib import Path
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
    status,
)
from fastapi.responses import (
    FileResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.config import Settings, get_settings
from app.database.models import (
    Publication,
    PublicationStatus,
)
from app.database.repositories.channel_repository import (
    ChannelRepository,
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

CONTENT_TYPE_LABELS = {
    "text": "Текст",
    "photo": "Фотография",
    "video": "Видео",
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

    return {
        "status": "ok",
        "database": "ok",
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
                "has_media": bool(publication.telegram_file_id),
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
        "has_media": bool(
            publication.telegram_file_id
            and publication.content_type in MEDIA_CONTENT_TYPES
        ),
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

        next_version = await publication_repository.update_scheduled(
            publication,
            channel_id=channel.id,
            text=normalized_text,
            text_entities_json=entities_json,
            scheduled_at_utc=(scheduled_at_utc),
            expected_version=payload.expected_version,
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


@app.get("/api/publications/{publication_id}/media")
async def get_publication_media(
    publication_id: int,
    telegram_init_data: str = Header(
        alias="X-Telegram-Init-Data",
    ),
) -> Response:
    settings = get_settings()
    user = authenticate_telegram_user(
        telegram_init_data,
        settings=settings,
    )
    owner_telegram_id = int(user["id"])

    publication = await get_owned_scheduled_publication(
        publication_id=publication_id,
        owner_telegram_id=(owner_telegram_id),
    )

    if (
        not publication.telegram_file_id
        or publication.content_type not in MEDIA_CONTENT_TYPES
    ):
        raise HTTPException(
            status_code=(status.HTTP_404_NOT_FOUND),
            detail=("У публикации нет доступного вложения."),
        )

    bot = Bot(token=(settings.bot_token.get_secret_value()))
    buffer = BytesIO()

    try:
        telegram_file = await bot.get_file(publication.telegram_file_id)

        if not telegram_file.file_path:
            raise HTTPException(
                status_code=(status.HTTP_502_BAD_GATEWAY),
                detail=("Telegram не вернул путь к вложению."),
            )

        await bot.download_file(
            telegram_file.file_path,
            destination=buffer,
        )
    except TelegramAPIError as error:
        raise HTTPException(
            status_code=(status.HTTP_502_BAD_GATEWAY),
            detail=("Не удалось получить вложение из Telegram."),
        ) from error
    finally:
        await bot.session.close()

    return Response(
        content=buffer.getvalue(),
        media_type=MEDIA_CONTENT_TYPES[publication.content_type],
        headers={
            "Cache-Control": ("private, max-age=60"),
        },
    )
