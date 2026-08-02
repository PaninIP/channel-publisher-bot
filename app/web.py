from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
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


class PublicationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_id: int = Field(gt=0)
    text: str | None = Field(
        default=None,
        max_length=4096,
    )
    scheduled_local: str = Field(
        min_length=16,
        max_length=32,
    )
    timezone: str = Field(
        min_length=1,
        max_length=64,
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


def get_application_timezone(
    settings: Settings,
) -> ZoneInfo:
    try:
        return ZoneInfo(settings.app_timezone.strip())
    except ZoneInfoNotFoundError as error:
        raise HTTPException(
            status_code=(status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=("На сервере некорректно настроен APP_TIMEZONE."),
        ) from error


def get_month_bounds_utc(
    month_value: str,
    *,
    timezone: ZoneInfo,
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
    timezone: ZoneInfo,
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
    return {"status": "ok"}


@app.get("/api/content-plan")
async def get_content_plan(
    month: str = Query(
        pattern=r"^\d{4}-\d{2}$",
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
    timezone = get_application_timezone(settings)
    utc_start, utc_end = get_month_bounds_utc(
        month,
        timezone=timezone,
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
            timezone=timezone,
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
        "timezone": (settings.app_timezone.strip()),
        "items": items,
    }


@app.get("/api/publications/{publication_id}")
async def get_publication_details(
    publication_id: int,
    telegram_init_data: str = Header(
        alias="X-Telegram-Init-Data",
    ),
) -> dict[str, object]:
    settings = get_settings()
    user = authenticate_telegram_user(
        telegram_init_data,
        settings=settings,
    )
    timezone = get_application_timezone(settings)
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
        timezone=timezone,
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
        "scheduled_local": (scheduled_local.strftime("%Y-%m-%dT%H:%M")),
        "timezone": (settings.app_timezone.strip()),
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
            scheduled_at_utc = parse_scheduled_local(
                payload.scheduled_local,
                timezone_name=(payload.timezone),
                configured_timezone_name=(settings.app_timezone),
            )
        except ContentPlanEditorValidationError as error:
            raise HTTPException(
                status_code=(status.HTTP_422_UNPROCESSABLE_ENTITY),
                detail=str(error),
            ) from error

        await publication_repository.update_scheduled(
            publication,
            channel_id=channel.id,
            text=normalized_text,
            scheduled_at_utc=(scheduled_at_utc),
        )

    return {
        "status": "updated",
        "publication_id": publication_id,
    }


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
