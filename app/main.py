import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers.publication import (
    router as publication_router,
)
from app.bot.handlers.settings import (
    router as settings_router,
)
from app.bot.handlers.start import router as start_router
from app.config import get_settings
from app.database.session import init_database


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        ),
    )

    settings = get_settings()

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dispatcher = Dispatcher()

    dispatcher.include_router(start_router)
    dispatcher.include_router(settings_router)
    dispatcher.include_router(publication_router)

    await init_database()

    await bot.delete_webhook(
        drop_pending_updates=True,
    )

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())