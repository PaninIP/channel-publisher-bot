from datetime import UTC, datetime, timedelta

import pytest

from app.services.content_plan_editor import (
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


def test_media_publication_allows_empty_caption() -> None:
    assert (
        normalize_publication_text(
            None,
            content_type="photo",
        )
        is None
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
        timezone_name="Europe/Moscow",
        configured_timezone_name=("Europe/Moscow"),
        now=now,
    )

    expected = datetime(
        2026,
        8,
        2,
        13,
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
            configured_timezone_name="UTC",
            now=now,
        )
