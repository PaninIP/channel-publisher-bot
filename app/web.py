from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database.repositories.channel_repository import (
    ChannelRepository,
)
from app.database.repositories.publication_repository import (
    PublicationRepository,
)
from app.database.session import SessionFactory
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Месяц должен иметь формат YYYY-MM.",
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

    utc_start = local_start.astimezone(UTC).replace(tzinfo=None)
    utc_end = local_end.astimezone(UTC).replace(tzinfo=None)

    return utc_start, utc_end


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

    try:
        user = validate_telegram_init_data(
            telegram_init_data,
            bot_token=(settings.bot_token.get_secret_value()),
            max_age_seconds=(settings.mini_app_auth_max_age_seconds),
        )
    except TelegramWebAppAuthError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error

    try:
        timezone = ZoneInfo(settings.app_timezone.strip())
    except ZoneInfoNotFoundError as error:
        raise HTTPException(
            status_code=(status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=("На сервере некорректно настроен APP_TIMEZONE."),
        ) from error

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
            for channel in await channel_repository.list_by_owner(
                owner_telegram_id,
            )
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
            }
        )

    return {
        "month": month,
        "timezone": (settings.app_timezone.strip()),
        "items": items,
    }
