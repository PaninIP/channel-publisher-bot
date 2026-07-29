import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers.content_plan import (
    router as content_plan_router,
)
from app.bot.handlers.publication import (
    router as publication_router,
)
from app.bot.handlers.scheduling import (
    router as scheduling_router,
)
from app.bot.handlers.settings import (
    router as settings_router,
)
from app.bot.handlers.start import router as start_router
from app.config import get_settings
from app.database.session import (
    close_database,
    init_database,
)
from app.workers.publication_worker import (
    run_publication_worker,
)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=("%(asctime)s | %(levelname)s | %(name)s | %(message)s"),
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
    dispatcher.include_router(content_plan_router)
    dispatcher.include_router(publication_router)
    dispatcher.include_router(scheduling_router)

    worker_task: asyncio.Task[None] | None = None

    try:
        await init_database()

        await bot.delete_webhook(
            drop_pending_updates=True,
        )

        worker_task = asyncio.create_task(
            run_publication_worker(
                bot=bot,
                interval_seconds=(settings.publication_worker_interval_seconds),
            ),
            name="publication-worker",
        )

        await dispatcher.start_polling(
            bot,
            close_bot_session=False,
        )

    finally:
        if worker_task is not None:
            worker_task.cancel()

            with suppress(asyncio.CancelledError):
                await worker_task

        await bot.session.close()
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
