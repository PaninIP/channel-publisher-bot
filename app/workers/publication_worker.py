import asyncio
import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.database.models import PublicationStatus
from app.database.repositories.channel_repository import (
    ChannelRepository,
)
from app.database.repositories.publication_repository import (
    PublicationRepository,
)
from app.database.session import SessionFactory
from app.services.publication_sender import (
    send_publication,
)

logger = logging.getLogger(__name__)


async def notify_owner(
    *,
    bot: Bot,
    owner_telegram_id: int,
    text: str,
) -> None:
    try:
        await bot.send_message(
            chat_id=owner_telegram_id,
            text=text,
        )
    except TelegramAPIError:
        logger.exception(
            "Failed to notify publication owner %s",
            owner_telegram_id,
        )


async def mark_failed(
    *,
    publication_id: int,
    owner_telegram_id: int,
    error_text: str,
) -> None:
    async with SessionFactory() as session:
        repository = PublicationRepository(session)

        publication = await repository.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )

        if publication is not None:
            await repository.mark_failed(
                publication,
                error_text=error_text,
            )


async def process_publication(
    *,
    bot: Bot,
    publication_id: int,
    owner_telegram_id: int,
) -> None:
    async with SessionFactory() as session:
        publication_repository = PublicationRepository(session)
        channel_repository = ChannelRepository(session)

        publication = await publication_repository.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )

        if publication is None:
            return

        if publication.status != PublicationStatus.SCHEDULED.value:
            return

        channel = await channel_repository.get_by_id(
            channel_id=publication.channel_id,
            owner_telegram_id=owner_telegram_id,
        )

        if channel is None:
            await publication_repository.mark_failed(
                publication,
                error_text=("Канал публикации не найден или был отключён."),
            )

            await notify_owner(
                bot=bot,
                owner_telegram_id=owner_telegram_id,
                text=(
                    "❌ Не удалось опубликовать "
                    f"запланированный пост #{publication_id}.\n\n"
                    "Канал был отключён или удалён."
                ),
            )
            return

        await publication_repository.mark_publishing(
            publication,
        )

        chat_id = channel.telegram_chat_id
        channel_title = channel.title
        content_type = publication.content_type
        text = publication.text
        telegram_file_id = publication.telegram_file_id

    try:
        published_message = await send_publication(
            bot=bot,
            chat_id=chat_id,
            content_type=content_type,
            text=text,
            telegram_file_id=telegram_file_id,
        )

    except (TelegramAPIError, ValueError) as error:
        logger.exception(
            "Scheduled publication %s failed",
            publication_id,
        )

        await mark_failed(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
            error_text=str(error),
        )

        await notify_owner(
            bot=bot,
            owner_telegram_id=owner_telegram_id,
            text=(
                "❌ <b>Не удалось опубликовать "
                "запланированный пост</b>\n\n"
                f"Публикация: "
                f"<code>{publication_id}</code>\n"
                f"Канал: "
                f"<b>{escape(channel_title)}</b>\n"
                f"Ошибка: "
                f"<code>{escape(str(error)[:500])}</code>"
            ),
        )
        return

    async with SessionFactory() as session:
        repository = PublicationRepository(session)

        publication = await repository.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )

        if publication is not None:
            await repository.mark_published(
                publication,
                telegram_message_id=(published_message.message_id),
            )

    await notify_owner(
        bot=bot,
        owner_telegram_id=owner_telegram_id,
        text=(
            "✅ <b>Запланированный пост опубликован</b>\n\n"
            f"Публикация: "
            f"<code>{publication_id}</code>\n"
            f"Канал: "
            f"<b>{escape(channel_title)}</b>\n"
            f"ID сообщения: "
            f"<code>{published_message.message_id}</code>"
        ),
    )


async def process_due_publications(
    bot: Bot,
) -> None:
    async with SessionFactory() as session:
        repository = PublicationRepository(session)

        due_publications = await repository.list_due_scheduled()

        publication_keys = [
            (
                publication.id,
                publication.owner_telegram_id,
            )
            for publication in due_publications
        ]

    for publication_id, owner_telegram_id in publication_keys:
        await process_publication(
            bot=bot,
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )


async def run_publication_worker(
    *,
    bot: Bot,
    interval_seconds: int,
) -> None:
    logger.info(
        "Publication worker started with interval %s seconds",
        interval_seconds,
    )

    while True:
        try:
            await process_due_publications(bot)

        except asyncio.CancelledError:
            logger.info("Publication worker stopped")
            raise

        except Exception:
            logger.exception("Unexpected publication worker error")

        await asyncio.sleep(interval_seconds)
