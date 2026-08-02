from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ContentPlanEditorValidationError(ValueError):
    pass


def normalize_publication_text(
    text: str | None,
    *,
    content_type: str,
) -> str | None:
    normalized = text.strip() if text else None

    if content_type == "text" and not normalized:
        raise ContentPlanEditorValidationError(
            "Текстовая публикация не может быть пустой."
        )

    return normalized


def parse_scheduled_local(
    scheduled_local: str,
    *,
    timezone_name: str,
    configured_timezone_name: str,
    minimum_delay_seconds: int = 60,
    now: datetime | None = None,
) -> datetime:
    requested_timezone = timezone_name.strip()
    configured_timezone = configured_timezone_name.strip()

    if requested_timezone != configured_timezone:
        raise ContentPlanEditorValidationError(
            "Часовой пояс Mini App не совпадает с настройками сервера."
        )

    try:
        timezone = ZoneInfo(configured_timezone)
    except ZoneInfoNotFoundError as error:
        raise ContentPlanEditorValidationError(
            "На сервере некорректно настроен часовой пояс."
        ) from error

    try:
        selected_naive = datetime.fromisoformat(scheduled_local)
    except ValueError as error:
        raise ContentPlanEditorValidationError(
            "Не удалось распознать дату и время."
        ) from error

    if selected_naive.tzinfo is not None:
        selected_naive = selected_naive.replace(tzinfo=None)

    selected_local = selected_naive.replace(tzinfo=timezone)

    current_time = now or datetime.now(timezone)

    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone)
    else:
        current_time = current_time.astimezone(timezone)

    minimum_time = current_time + timedelta(seconds=minimum_delay_seconds)

    if selected_local <= minimum_time:
        raise ContentPlanEditorValidationError(
            "Выберите время минимум на одну минуту позже текущего."
        )

    return selected_local.astimezone(UTC).replace(tzinfo=None)
