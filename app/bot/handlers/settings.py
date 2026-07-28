from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
)
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.main_menu import get_main_menu
from app.bot.keyboards.settings import (
    CHANNEL_REQUEST_ID,
    get_channel_selector_keyboard,
    get_channels_keyboard,
    get_settings_keyboard,
)
from app.database.models import Channel
from app.database.repositories.channel_repository import (
    ChannelRepository,
)
from app.database.session import SessionFactory


router = Router(name=__name__)


def format_channels(channels: list[Channel]) -> str:
    if not channels:
        return (
            "📢 <b>Ваши каналы</b>\n\n"
            "У вас пока нет подключённых каналов.\n\n"
            "Нажмите «➕ Добавить канал», выберите канал "
            "и разрешите боту публиковать сообщения."
        )

    lines = [
        "📢 <b>Ваши каналы</b>",
        "",
    ]

    for number, channel in enumerate(channels, start=1):
        safe_title = escape(channel.title)

        if channel.username:
            address = f"@{escape(channel.username)}"
        else:
            address = "Приватный канал"

        lines.append(
            f"{number}. 🟢 <b>{safe_title}</b>\n"
            f"   {address}"
        )

    lines.append("")
    lines.append(
        "🟢 Канал подключён и доступен для публикаций."
    )

    return "\n".join(lines)


async def get_owner_channels(
    owner_telegram_id: int,
) -> list[Channel]:
    async with SessionFactory() as session:
        repository = ChannelRepository(session)

        return await repository.list_by_owner(
            owner_telegram_id=owner_telegram_id,
        )


@router.message(F.text == "⚙️ Настройки")
async def handle_settings(message: Message) -> None:
    await message.answer(
        text=(
            "⚙️ <b>Настройки</b>\n\n"
            "Здесь можно подключать каналы и управлять "
            "параметрами бота."
        ),
        reply_markup=get_settings_keyboard(),
    )


@router.callback_query(F.data == "settings:channels")
async def handle_channels(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return

    channels = await get_owner_channels(
        owner_telegram_id=callback.from_user.id,
    )

    await callback.message.edit_text(
        text=format_channels(channels),
        reply_markup=get_channels_keyboard(),
    )

    await callback.answer()


@router.callback_query(F.data == "channels:back")
async def handle_channels_back(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await callback.message.edit_text(
        text=(
            "⚙️ <b>Настройки</b>\n\n"
            "Здесь можно подключать каналы и управлять "
            "параметрами бота."
        ),
        reply_markup=get_settings_keyboard(),
    )

    await callback.answer()


@router.callback_query(F.data == "channels:add")
async def handle_add_channel(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await callback.message.answer(
        text=(
            "➕ <b>Добавление канала</b>\n\n"
            "1. Нажмите кнопку «📢 Выбрать канал».\n"
            "2. Выберите канал, которым вы управляете.\n"
            "3. Подтвердите добавление бота.\n\n"
            "Боту потребуется право публикации сообщений."
        ),
        reply_markup=get_channel_selector_keyboard(),
    )

    await callback.answer()


@router.message(F.text == "❌ Отмена")
async def handle_add_channel_cancel(
    message: Message,
) -> None:
    await message.answer(
        text="Добавление канала отменено.",
        reply_markup=get_main_menu(),
    )


@router.message(F.chat_shared)
async def handle_shared_channel(
    message: Message,
    bot: Bot,
) -> None:
    shared_chat = message.chat_shared

    if shared_chat is None:
        return

    if shared_chat.request_id != CHANNEL_REQUEST_ID:
        return

    if message.from_user is None:
        await message.answer(
            "Не удалось определить пользователя."
        )
        return

    try:
        bot_user = await bot.get_me()

        chat = await bot.get_chat(
            chat_id=shared_chat.chat_id,
        )

        bot_member = await bot.get_chat_member(
            chat_id=shared_chat.chat_id,
            user_id=bot_user.id,
        )

    except TelegramForbiddenError:
        await message.answer(
            text=(
                "❌ Бот не имеет доступа к этому каналу.\n\n"
                "Добавьте бота в канал как администратора "
                "с правом публикации сообщений."
            ),
            reply_markup=get_main_menu(),
        )
        return

    except TelegramBadRequest as error:
        await message.answer(
            text=(
                "❌ Telegram не позволил подключить канал.\n\n"
                f"Причина: <code>{escape(str(error))}</code>"
            ),
            reply_markup=get_main_menu(),
        )
        return

    if chat.type != ChatType.CHANNEL:
        await message.answer(
            text="❌ Выбранный чат не является каналом.",
            reply_markup=get_main_menu(),
        )
        return

    is_administrator = bot_member.status in {
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    }

    can_post_messages = bool(
        getattr(bot_member, "can_post_messages", False)
    )

    if not is_administrator or not can_post_messages:
        await message.answer(
            text=(
                "❌ Бот добавлен без необходимых прав.\n\n"
                "Откройте управление каналом и разрешите боту "
                "публиковать сообщения."
            ),
            reply_markup=get_main_menu(),
        )
        return

    async with SessionFactory() as session:
        repository = ChannelRepository(session)

        channel = await repository.add_or_update(
            owner_telegram_id=message.from_user.id,
            telegram_chat_id=chat.id,
            title=chat.title or "Канал без названия",
            username=chat.username,
        )

    if channel.username:
        channel_address = f"@{escape(channel.username)}"
    else:
        channel_address = "приватный канал"

    await message.answer(
        text=(
            "✅ <b>Канал успешно подключён</b>\n\n"
            f"Название: <b>{escape(channel.title)}</b>\n"
            f"Адрес: {channel_address}\n"
            f"ID: <code>{channel.telegram_chat_id}</code>\n\n"
            "Теперь бот сможет публиковать в этот канал."
        ),
        reply_markup=get_main_menu(),
    )