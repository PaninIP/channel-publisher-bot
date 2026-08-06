from datetime import UTC, datetime, timedelta

import pytest

from app.services.content_plan_editor import (
    MEDIA_CAPTION_MAX_LENGTH,
    TEXT_MAX_LENGTH,
    ContentPlanEditorValidationError,
    normalize_publication_text,
    parse_scheduled_local,
)


def test_text_publication_requires_text() -> None:
    with pytest.raises(ContentPlanEditorValidationError):
        normalize_publication_text(
            "   ",
            content_type="text",
        )


def test_text_publication_accepts_telegram_limit() -> None:
    text = "x" * TEXT_MAX_LENGTH

    assert (
        normalize_publication_text(
            text,
            content_type="text",
        )
        == text
    )


def test_text_publication_rejects_text_above_telegram_limit() -> None:
    with pytest.raises(
        ContentPlanEditorValidationError,
        match="4096",
    ):
        normalize_publication_text(
            "x" * (TEXT_MAX_LENGTH + 1),
            content_type="text",
        )


def test_media_publication_allows_empty_caption() -> None:
    assert (
        normalize_publication_text(
            None,
            content_type="photo",
        )
        is None
    )


def test_media_publication_accepts_caption_limit() -> None:
    caption = "x" * MEDIA_CAPTION_MAX_LENGTH

    assert (
        normalize_publication_text(
            caption,
            content_type="video",
        )
        == caption
    )


def test_media_publication_rejects_caption_above_limit() -> None:
    with pytest.raises(
        ContentPlanEditorValidationError,
        match="1024",
    ):
        normalize_publication_text(
            "x" * (MEDIA_CAPTION_MAX_LENGTH + 1),
            content_type="photo",
        )


def test_unknown_content_type_is_rejected() -> None:
    with pytest.raises(
        ContentPlanEditorValidationError,
        match="Неизвестный тип публикации",
    ):
        normalize_publication_text(
            "text",
            content_type="document",
        )


def test_schedule_is_converted_to_naive_utc() -> None:
    now = datetime(
        2026,
        8,
        2,
        12,
        0,
        tzinfo=UTC,
    )

    result = parse_scheduled_local(
        "2026-08-02T16:30",
        timezone_name="Europe/Samara",
        timezone_offset_minutes=240,
        now=now,
    )

    expected = datetime(
        2026,
        8,
        2,
        12,
        30,
        tzinfo=UTC,
    ).replace(tzinfo=None)

    assert result == expected
    assert result.tzinfo is None


def test_past_schedule_is_rejected() -> None:
    now = datetime.now(UTC)

    with pytest.raises(ContentPlanEditorValidationError):
        parse_scheduled_local(
            (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M"),
            timezone_name="UTC",
            timezone_offset_minutes=0,
            now=now,
        )


def test_next_device_minute_is_allowed() -> None:
    now = datetime(
        2026,
        8,
        6,
        17,
        55,
        40,
        tzinfo=UTC,
    )

    result = parse_scheduled_local(
        "2026-08-06T21:56",
        timezone_name="Europe/Samara",
        timezone_offset_minutes=240,
        now=now,
    )

    assert result == datetime(2026, 8, 6, 17, 56)


def test_current_device_minute_is_rejected() -> None:
    now = datetime(
        2026,
        8,
        6,
        17,
        55,
        1,
        tzinfo=UTC,
    )

    with pytest.raises(
        ContentPlanEditorValidationError,
        match="следующая минута",
    ):
        parse_scheduled_local(
            "2026-08-06T21:55",
            timezone_name="Europe/Samara",
            timezone_offset_minutes=240,
            now=now,
        )


def test_device_timezone_offset_mismatch_is_rejected() -> None:
    with pytest.raises(
        ContentPlanEditorValidationError,
        match="Часовой пояс устройства изменился",
    ):
        parse_scheduled_local(
            "2026-08-06T21:56",
            timezone_name="Europe/Samara",
            timezone_offset_minutes=180,
            now=datetime(2026, 8, 6, 17, 0, tzinfo=UTC),
        )
