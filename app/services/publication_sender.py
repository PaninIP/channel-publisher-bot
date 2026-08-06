from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import (
    FSInputFile,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from app.config import Settings
from app.database.models import (
    PublicationContentType,
    PublicationMedia,
)
from app.services.media_storage import get_media_storage_for_backend
from app.services.telegram_entities import build_aiogram_entities


@dataclass(slots=True)
class PublicationSendResult:
    messages: list[Message]
    file_ids_by_media_id: dict[int, str]

    @property
    def primary_message(self) -> Message:
        return self.messages[0]

    @property
    def message_ids(self) -> list[int]:
        return [message.message_id for message in self.messages]


def extract_message_file_id(message: Message, media_type: str) -> str | None:
    if media_type == PublicationContentType.PHOTO.value and message.photo:
        return message.photo[-1].file_id
    if media_type == PublicationContentType.VIDEO.value and message.video:
        return message.video.file_id
    return None


async def _materialize_input(
    *,
    media: PublicationMedia,
    settings: Settings,
    temporary_paths: list[Path],
) -> str | FSInputFile:
    if media.telegram_file_id:
        return media.telegram_file_id
    if not media.storage_key:
        raise ValueError(f"У вложения #{media.id} отсутствует файл.")
    if media.storage_backend == "telegram":
        raise ValueError(f"У вложения #{media.id} отсутствует Telegram file_id.")

    suffix = Path(media.original_filename or "").suffix
    temporary = tempfile.NamedTemporaryFile(
        prefix=f"publication-media-{media.id}-",
        suffix=suffix,
        delete=False,
    )
    temporary.close()
    temporary_path = Path(temporary.name)
    temporary_paths.append(temporary_path)

    storage = get_media_storage_for_backend(settings, media.storage_backend)
    await storage.download_to_path(
        storage_key=media.storage_key,
        destination_path=temporary_path,
    )
    return FSInputFile(
        temporary_path,
        filename=media.original_filename or temporary_path.name,
    )


async def send_publication(
    *,
    bot: Bot,
    chat_id: int,
    content_type: str,
    text: str | None,
    telegram_file_id: str | None,
    text_entities_json: str | None = None,
    media_items: list[PublicationMedia] | None = None,
    settings: Settings | None = None,
    show_caption_above_media: bool = False,
) -> PublicationSendResult:
    entities = build_aiogram_entities(text, text_entities_json) if text else None
    media = list(media_items or [])

    if not media and telegram_file_id and content_type in {"photo", "video"}:
        media = [
            PublicationMedia(
                id=0,
                publication_id=0,
                owner_telegram_id=0,
                media_type=content_type,
                storage_backend="telegram",
                telegram_file_id=telegram_file_id,
                position=1,
            )
        ]

    if not media:
        if content_type != PublicationContentType.TEXT.value:
            raise ValueError("У медиапубликации отсутствуют вложения.")
        if not text:
            raise ValueError("У текстовой публикации отсутствует текст.")

        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=None,
            entities=entities,
        )
        return PublicationSendResult([message], {})

    if settings is None:
        raise ValueError("Для отправки медиа не переданы настройки хранилища.")
    if len(media) > settings.media_max_items:
        raise ValueError(f"В публикации больше {settings.media_max_items} вложений.")

    media.sort(key=lambda item: (item.position, item.id))
    temporary_paths: list[Path] = []

    try:
        inputs = [
            await _materialize_input(
                media=item,
                settings=settings,
                temporary_paths=temporary_paths,
            )
            for item in media
        ]

        if len(media) == 1:
            item = media[0]
            input_file = inputs[0]
            if item.media_type == PublicationContentType.PHOTO.value:
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=input_file,
                    caption=text or None,
                    parse_mode=None,
                    caption_entities=entities,
                    show_caption_above_media=show_caption_above_media,
                    has_spoiler=item.has_spoiler,
                )
            elif item.media_type == PublicationContentType.VIDEO.value:
                message = await bot.send_video(
                    chat_id=chat_id,
                    video=input_file,
                    caption=text or None,
                    parse_mode=None,
                    caption_entities=entities,
                    show_caption_above_media=show_caption_above_media,
                    has_spoiler=item.has_spoiler,
                    supports_streaming=True,
                )
            else:
                raise ValueError(f"Неизвестный тип вложения: {item.media_type}")

            file_id = extract_message_file_id(message, item.media_type)
            return PublicationSendResult(
                [message],
                {item.id: file_id} if file_id and item.id else {},
            )

        telegram_media = []
        for index, (item, input_file) in enumerate(zip(media, inputs, strict=True)):
            caption = (text or None) if index == 0 else None
            caption_entities = entities if index == 0 else None
            if item.media_type == PublicationContentType.PHOTO.value:
                telegram_media.append(
                    InputMediaPhoto(
                        media=input_file,
                        caption=caption,
                        caption_entities=caption_entities,
                        show_caption_above_media=(
                            show_caption_above_media if index == 0 else False
                        ),
                        has_spoiler=item.has_spoiler,
                    )
                )
            elif item.media_type == PublicationContentType.VIDEO.value:
                telegram_media.append(
                    InputMediaVideo(
                        media=input_file,
                        caption=caption,
                        caption_entities=caption_entities,
                        show_caption_above_media=(
                            show_caption_above_media if index == 0 else False
                        ),
                        has_spoiler=item.has_spoiler,
                        supports_streaming=True,
                    )
                )
            else:
                raise ValueError(f"Неизвестный тип вложения: {item.media_type}")

        messages = list(
            await bot.send_media_group(
                chat_id=chat_id,
                media=telegram_media,
            )
        )
        file_ids: dict[int, str] = {}
        for item, message in zip(media, messages, strict=True):
            file_id = extract_message_file_id(message, item.media_type)
            if file_id:
                file_ids[item.id] = file_id
        return PublicationSendResult(messages, file_ids)
    finally:
        for path in temporary_paths:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
