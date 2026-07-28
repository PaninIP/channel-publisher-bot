from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.keyboards.main_menu import get_main_menu


router = Router(name=__name__)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    text = (
        "👋 <b>Привет! Я помогу вести ваши Telegram-каналы.</b>\n\n"
        "📝 <b>Создать пост</b> — текст, фото или видео; "
        "публикация сразу или по расписанию.\n\n"
        "📅 <b>Контент-план</b> — список запланированных публикаций.\n\n"
        "✏️ <b>Изменить пост</b> — редактирование текста, медиа и времени.\n\n"
        "📊 <b>Статистика</b> — опубликованные и ожидающие посты.\n\n"
        "🤖 <b>Нейропостинг</b> — автоматический сбор, обработка "
        "и AI-рерайт публикаций.\n\n"
        "⚙️ <b>Настройки</b> — подключение и управление каналами.\n\n"
        "🚦 Для начала работы добавьте хотя бы один канал:\n"
        "<b>Настройки → Каналы → Добавить канал</b>."
    )

    await message.answer(
        text=text,
        reply_markup=get_main_menu(),
    )