from aiogram import Bot
from aiogram.types import Message

from app.database.models import PublicationContentType
from app.services.telegram_entities import build_aiogram_entities


async def send_publication(
    *,
    bot: Bot,
    chat_id: int,
    content_type: str,
    text: str | None,
    telegram_file_id: str | None,
    text_entities_json: str | None = None,
) -> Message:
    entities = build_aiogram_entities(text, text_entities_json) if text else None

    if content_type == PublicationContentType.TEXT.value:
        if not text:
            raise ValueError("У текстовой публикации отсутствует текст.")

        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=None,
            entities=entities,
        )

    if content_type == PublicationContentType.PHOTO.value:
        if not telegram_file_id:
            raise ValueError("У публикации отсутствует file_id фотографии.")

        return await bot.send_photo(
            chat_id=chat_id,
            photo=telegram_file_id,
            caption=text or None,
            parse_mode=None,
            caption_entities=entities,
        )

    if content_type == PublicationContentType.VIDEO.value:
        if not telegram_file_id:
            raise ValueError("У публикации отсутствует file_id видео.")

        return await bot.send_video(
            chat_id=chat_id,
            video=telegram_file_id,
            caption=text or None,
            parse_mode=None,
            caption_entities=entities,
            supports_streaming=True,
        )

    raise ValueError(f"Неизвестный тип публикации: {content_type}")
