from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

SUPPORTED_ENTITY_TYPES = frozenset(
    {
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
    }
)

BLOCK_ENTITY_TYPES = frozenset(
    {
        "blockquote",
        "expandable_blockquote",
        "pre",
    }
)

MONOSPACE_ENTITY_TYPES = frozenset({"code", "pre"})
FLEXIBLE_ENTITY_TYPES = frozenset(
    {
        "bold",
        "italic",
        "underline",
        "strikethrough",
        "spoiler",
    }
)


class TelegramEntityValidationError(ValueError):
    pass


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def utf16_boundaries(value: str) -> set[int]:
    boundaries = {0}
    current = 0

    for character in value:
        current += 2 if ord(character) > 0xFFFF else 1
        boundaries.add(current)

    return boundaries


def _normalize_url(value: Any) -> str:
    url = str(value or "").strip()

    if not url or len(url) > 2048:
        raise TelegramEntityValidationError(
            "Для ссылки укажите корректный URL длиной до 2048 символов."
        )

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https", "tg", "mailto"}:
        raise TelegramEntityValidationError(
            "Ссылка должна начинаться с http://, https://, tg:// или mailto:."
        )

    if parsed.scheme in {"http", "https"} and not parsed.netloc:
        raise TelegramEntityValidationError("У ссылки отсутствует домен.")

    return url


def _normalize_language(value: Any) -> str | None:
    language = str(value or "").strip()

    if not language:
        return None

    if len(language) > 64:
        raise TelegramEntityValidationError(
            "Название языка блока кода не должно быть длиннее 64 символов."
        )

    return language


def _ensure_non_crossing(entities: Sequence[dict[str, Any]]) -> None:
    stack: list[dict[str, Any]] = []

    for entity in entities:
        start = int(entity["offset"])
        end = start + int(entity["length"])

        while stack:
            parent = stack[-1]
            parent_end = int(parent["offset"]) + int(parent["length"])

            if start >= parent_end:
                stack.pop()
                continue

            break

        if stack:
            parent = stack[-1]
            parent_end = int(parent["offset"]) + int(parent["length"])

            if end > parent_end:
                raise TelegramEntityValidationError(
                    "Форматирование пересекается некорректно. "
                    "Снимите форматирование с этого фрагмента и примените заново."
                )

        stack.append(entity)


def _ensure_telegram_nesting_rules(
    entities: Sequence[dict[str, Any]],
) -> None:
    for index, left in enumerate(entities):
        left_start = int(left["offset"])
        left_end = left_start + int(left["length"])
        left_type = str(left["type"])

        for right in entities[index + 1 :]:
            right_start = int(right["offset"])
            right_end = right_start + int(right["length"])
            right_type = str(right["type"])

            if right_start >= left_end:
                break

            overlaps = left_start < right_end and right_start < left_end

            if not overlaps:
                continue

            if (
                left_type in MONOSPACE_ENTITY_TYPES
                or right_type in MONOSPACE_ENTITY_TYPES
            ):
                raise TelegramEntityValidationError(
                    "Моноширинный текст и блоки кода нельзя совмещать "
                    "с другим форматированием."
                )

            if left_type in BLOCK_ENTITY_TYPES and right_type in BLOCK_ENTITY_TYPES:
                raise TelegramEntityValidationError(
                    "Цитаты и блоки кода нельзя вкладывать друг в друга."
                )

            if (
                left_type not in FLEXIBLE_ENTITY_TYPES
                and right_type not in FLEXIBLE_ENTITY_TYPES
            ):
                raise TelegramEntityValidationError(
                    "Эти типы форматирования нельзя вкладывать друг в друга."
                )


def normalize_telegram_entities(
    text: str,
    raw_entities: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not raw_entities:
        return []

    total_length = utf16_length(text)
    boundaries = utf16_boundaries(text)
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[object, ...]] = set()

    for raw_entity in raw_entities:
        entity_type = str(raw_entity.get("type") or "").strip()

        if entity_type not in SUPPORTED_ENTITY_TYPES:
            raise TelegramEntityValidationError(
                f"Форматирование типа {entity_type or 'unknown'} не поддерживается."
            )

        try:
            offset = int(raw_entity.get("offset"))
            length = int(raw_entity.get("length"))
        except (TypeError, ValueError) as error:
            raise TelegramEntityValidationError(
                "Позиция форматирования должна быть целым числом."
            ) from error

        end = offset + length

        if offset < 0 or length <= 0 or end > total_length:
            raise TelegramEntityValidationError(
                "Форматирование выходит за границы текста."
            )

        if offset not in boundaries or end not in boundaries:
            raise TelegramEntityValidationError(
                "Форматирование разрывает составной символ или эмодзи."
            )

        entity: dict[str, Any] = {
            "type": entity_type,
            "offset": offset,
            "length": length,
        }

        if entity_type == "text_link":
            entity["url"] = _normalize_url(raw_entity.get("url"))

        if entity_type == "pre":
            language = _normalize_language(raw_entity.get("language"))

            if language:
                entity["language"] = language

        identity = (
            entity["type"],
            entity["offset"],
            entity["length"],
            entity.get("url"),
            entity.get("language"),
        )

        if identity in seen:
            continue

        seen.add(identity)
        normalized.append(entity)

    normalized.sort(
        key=lambda item: (
            int(item["offset"]),
            -int(item["length"]),
            str(item["type"]),
        )
    )

    _ensure_non_crossing(normalized)
    _ensure_telegram_nesting_rules(normalized)

    return normalized


def dump_telegram_entities(entities: Sequence[Mapping[str, Any]]) -> str | None:
    if not entities:
        return None

    return json.dumps(
        list(entities),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def load_telegram_entities(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []

    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise TelegramEntityValidationError(
            "Сохранённое форматирование повреждено."
        ) from error

    if not isinstance(payload, list):
        raise TelegramEntityValidationError(
            "Сохранённое форматирование имеет неверный формат."
        )

    result: list[dict[str, Any]] = []

    for entity in payload:
        if not isinstance(entity, dict):
            raise TelegramEntityValidationError(
                "Сохранённое форматирование имеет неверный формат."
            )

        result.append(dict(entity))

    return result


def build_aiogram_entities(
    text: str,
    entities_json: str | None,
) -> list[Any] | None:
    from aiogram.types import MessageEntity

    raw_entities = load_telegram_entities(entities_json)
    entities = normalize_telegram_entities(text, raw_entities)

    if not entities:
        return None

    return [MessageEntity(**entity) for entity in entities]
