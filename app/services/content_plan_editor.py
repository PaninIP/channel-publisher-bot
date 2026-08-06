from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TEXT_MAX_LENGTH = 4096
MEDIA_CAPTION_MAX_LENGTH = 1024
MEDIA_CONTENT_TYPES = {"photo", "video"}
MIN_TIMEZONE_OFFSET_MINUTES = -(14 * 60)
MAX_TIMEZONE_OFFSET_MINUTES = 14 * 60


class ContentPlanEditorValidationError(ValueError):
    pass


def normalize_publication_text(
    text: str | None,
    *,
    content_type: str,
) -> str | None:
    normalized = text.strip() if text else None

    if content_type == "text":
        if not normalized:
            raise ContentPlanEditorValidationError(
                "Текстовая публикация не может быть пустой."
            )

        if len(normalized) > TEXT_MAX_LENGTH:
            raise ContentPlanEditorValidationError(
                "Текст слишком длинный. Максимальная длина — 4096 символов."
            )

        return normalized

    if content_type in MEDIA_CONTENT_TYPES:
        if normalized and len(normalized) > MEDIA_CAPTION_MAX_LENGTH:
            raise ContentPlanEditorValidationError(
                "Подпись к фото или видео слишком длинная. "
                "Максимальная длина — 1024 символа."
            )

        return normalized

    raise ContentPlanEditorValidationError(
        f"Неизвестный тип публикации: {content_type}."
    )


def _validate_timezone_offset(timezone_offset_minutes: int) -> None:
    if not (
        MIN_TIMEZONE_OFFSET_MINUTES
        <= timezone_offset_minutes
        <= MAX_TIMEZONE_OFFSET_MINUTES
    ):
        raise ContentPlanEditorValidationError(
            "Устройство передало некорректное смещение часового пояса."
        )


def _build_selected_local_datetime(
    selected_naive: datetime,
    *,
    timezone_name: str,
    timezone_offset_minutes: int | None,
) -> datetime:
    requested_timezone = timezone_name.strip()

    if not requested_timezone:
        if timezone_offset_minutes is None:
            raise ContentPlanEditorValidationError(
                "Устройство не передало часовой пояс."
            )

        _validate_timezone_offset(timezone_offset_minutes)
        return selected_naive.replace(
            tzinfo=timezone(timedelta(minutes=timezone_offset_minutes))
        )

    try:
        device_timezone = ZoneInfo(requested_timezone)
    except ZoneInfoNotFoundError as error:
        raise ContentPlanEditorValidationError(
            "Устройство передало неизвестный часовой пояс."
        ) from error

    candidates = (
        selected_naive.replace(tzinfo=device_timezone, fold=0),
        selected_naive.replace(tzinfo=device_timezone, fold=1),
    )

    if timezone_offset_minutes is None:
        selected_local = candidates[0]
    else:
        _validate_timezone_offset(timezone_offset_minutes)
        matching_candidates = [
            candidate
            for candidate in candidates
            if candidate.utcoffset() is not None
            and int(candidate.utcoffset().total_seconds() // 60)
            == timezone_offset_minutes
        ]

        if not matching_candidates:
            raise ContentPlanEditorValidationError(
                "Часовой пояс устройства изменился. Закройте и снова откройте Mini App."
            )

        selected_local = matching_candidates[0]
    round_trip = selected_local.astimezone(UTC).astimezone(device_timezone)

    if round_trip.replace(tzinfo=None) != selected_naive:
        raise ContentPlanEditorValidationError(
            "Выбранное локальное время не существует из-за перевода часов."
        )

    return selected_local


def parse_scheduled_local(
    scheduled_local: str,
    *,
    timezone_name: str,
    timezone_offset_minutes: int | None,
    minimum_delay_seconds: int = 0,
    now: datetime | None = None,
) -> datetime:
    try:
        selected_naive = datetime.fromisoformat(scheduled_local)
    except ValueError as error:
        raise ContentPlanEditorValidationError(
            "Не удалось распознать дату и время."
        ) from error

    if selected_naive.tzinfo is not None:
        selected_naive = selected_naive.replace(tzinfo=None)

    selected_local = _build_selected_local_datetime(
        selected_naive,
        timezone_name=timezone_name,
        timezone_offset_minutes=timezone_offset_minutes,
    )
    selected_utc = selected_local.astimezone(UTC)

    current_time = now or datetime.now(UTC)

    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    else:
        current_time = current_time.astimezone(UTC)

    minimum_time = current_time + timedelta(seconds=max(0, minimum_delay_seconds))

    if selected_utc <= minimum_time:
        raise ContentPlanEditorValidationError(
            "Выберите будущую дату и время. "
            "Ближайший доступный вариант — следующая минута."
        )

    return selected_utc.replace(tzinfo=None)
