import pytest

from app.services.telegram_entities import (
    TelegramEntityValidationError,
    dump_telegram_entities,
    load_telegram_entities,
    normalize_telegram_entities,
    utf16_length,
)


def test_utf16_length_counts_emoji_as_two_units() -> None:
    assert utf16_length("A😀B") == 4


def test_supported_entities_are_normalized() -> None:
    text = "Жирный и ссылка"
    entities = normalize_telegram_entities(
        text,
        [
            {"type": "bold", "offset": 0, "length": 6},
            {
                "type": "text_link",
                "offset": 9,
                "length": 6,
                "url": "https://example.com",
            },
        ],
    )

    assert entities == [
        {"type": "bold", "offset": 0, "length": 6},
        {
            "type": "text_link",
            "offset": 9,
            "length": 6,
            "url": "https://example.com",
        },
    ]


def test_entity_cannot_split_emoji_surrogate_pair() -> None:
    with pytest.raises(
        TelegramEntityValidationError,
        match="эмодзи",
    ):
        normalize_telegram_entities(
            "A😀B",
            [{"type": "bold", "offset": 1, "length": 1}],
        )


def test_crossing_entities_are_rejected() -> None:
    with pytest.raises(
        TelegramEntityValidationError,
        match="пересекается",
    ):
        normalize_telegram_entities(
            "abcdefghij",
            [
                {"type": "bold", "offset": 0, "length": 6},
                {"type": "italic", "offset": 4, "length": 5},
            ],
        )


def test_code_cannot_overlap_other_formatting() -> None:
    with pytest.raises(
        TelegramEntityValidationError,
        match="Моноширинный",
    ):
        normalize_telegram_entities(
            "abcdef",
            [
                {"type": "code", "offset": 0, "length": 6},
                {"type": "bold", "offset": 0, "length": 6},
            ],
        )


def test_text_link_requires_supported_scheme() -> None:
    with pytest.raises(
        TelegramEntityValidationError,
        match="начинаться",
    ):
        normalize_telegram_entities(
            "ссылка",
            [
                {
                    "type": "text_link",
                    "offset": 0,
                    "length": 6,
                    "url": "javascript:alert(1)",
                }
            ],
        )


def test_entities_json_round_trip() -> None:
    entities = [
        {"type": "spoiler", "offset": 0, "length": 4},
        {
            "type": "pre",
            "offset": 5,
            "length": 4,
            "language": "python",
        },
    ]

    dumped = dump_telegram_entities(entities)

    assert dumped is not None
    assert load_telegram_entities(dumped) == entities


def test_bold_can_be_nested_inside_blockquote() -> None:
    entities = normalize_telegram_entities(
        "abcdef",
        [
            {"type": "blockquote", "offset": 0, "length": 6},
            {"type": "bold", "offset": 1, "length": 4},
        ],
    )

    assert entities == [
        {"type": "blockquote", "offset": 0, "length": 6},
        {"type": "bold", "offset": 1, "length": 4},
    ]


def test_non_flexible_entities_cannot_be_nested() -> None:
    with pytest.raises(
        TelegramEntityValidationError,
        match="нельзя вкладывать",
    ):
        normalize_telegram_entities(
            "abcdef",
            [
                {
                    "type": "text_link",
                    "offset": 0,
                    "length": 6,
                    "url": "https://example.com",
                },
                {"type": "blockquote", "offset": 1, "length": 4},
            ],
        )
