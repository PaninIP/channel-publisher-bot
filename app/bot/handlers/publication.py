from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
)
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardRemove,
)

from app.bot.keyboards.main_menu import get_main_menu
from app.bot.keyboards.publication import (
    get_post_channel_keyboard,
    get_post_confirmation_keyboard,
    get_post_content_keyboard,
)
from app.bot.states.publication import CreatePost
from app.database.models import (
    Channel,
    PublicationContentType,
    PublicationStatus,
)
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


router = Router(name=__name__)


async def get_owner_channels(
    owner_telegram_id: int,
) -> list[Channel]:
    async with SessionFactory() as session:
        repository = ChannelRepository(session)

        return await repository.list_by_owner(
            owner_telegram_id=owner_telegram_id,
        )


async def get_owner_channel(
    *,
    channel_id: int,
    owner_telegram_id: int,
) -> Channel | None:
    async with SessionFactory() as session:
        repository = ChannelRepository(session)

        return await repository.get_by_id(
            channel_id=channel_id,
            owner_telegram_id=owner_telegram_id,
        )


async def mark_publication_failed(
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


def extract_content(
    message: Message,
) -> tuple[str, str | None, str | None] | None:
    if message.photo:
        largest_photo = message.photo[-1]
        caption = (message.caption or "").strip()

        return (
            PublicationContentType.PHOTO.value,
            caption or None,
            largest_photo.file_id,
        )

    if message.video:
        caption = (message.caption or "").strip()

        return (
            PublicationContentType.VIDEO.value,
            caption or None,
            message.video.file_id,
        )

    if message.text:
        text = message.text.strip()

        if text:
            return (
                PublicationContentType.TEXT.value,
                text,
                None,
            )

    return None


def validate_content(
    *,
    content_type: str,
    text: str | None,
) -> str | None:
    if content_type == PublicationContentType.TEXT.value:
        if not text:
            return "Текст публикации не должен быть пустым."

        if len(text) > 4096:
            return (
                "Текст слишком длинный. "
                "Максимальная длина — 4096 символов."
            )

    if content_type in {
        PublicationContentType.PHOTO.value,
        PublicationContentType.VIDEO.value,
    }:
        if text and len(text) > 1024:
            return (
                "Подпись к фото или видео слишком длинная. "
                "Максимальная длина — 1024 символа."
            )

    return None


async def send_preview(
    *,
    message: Message,
    content_type: str,
    text: str | None,
    telegram_file_id: str | None,
) -> None:
    keyboard = get_post_confirmation_keyboard()

    if content_type == PublicationContentType.TEXT.value:
        await message.answer(
            text=text or "",
            parse_mode=None,
            reply_markup=keyboard,
        )
        return

    if (
        content_type
        == PublicationContentType.PHOTO.value
        and telegram_file_id
    ):
        await message.answer_photo(
            photo=telegram_file_id,
            caption=text or None,
            parse_mode=None,
            reply_markup=keyboard,
        )
        return

    if (
        content_type
        == PublicationContentType.VIDEO.value
        and telegram_file_id
    ):
        await message.answer_video(
            video=telegram_file_id,
            caption=text or None,
            parse_mode=None,
            supports_streaming=True,
            reply_markup=keyboard,
        )
        return

    raise ValueError(
        "Не удалось сформировать предпросмотр."
    )


@router.message(F.text == "📝 Создать пост")
async def handle_create_post(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        await message.answer(
            "Не удалось определить пользователя."
        )
        return

    channels = await get_owner_channels(
        owner_telegram_id=message.from_user.id,
    )

    if not channels:
        await message.answer(
            text=(
                "❌ У вас пока нет подключённых каналов.\n\n"
                "Сначала добавьте канал:\n"
                "<b>⚙️ Настройки → 📢 Каналы "
                "→ ➕ Добавить канал</b>."
            ),
            reply_markup=get_main_menu(),
        )
        return

    await state.clear()
    await state.set_state(
        CreatePost.waiting_for_content,
    )

    await message.answer(
        text=(
            "📝 <b>Создание поста</b>\n\n"
            "Отправьте одним сообщением:\n\n"
            "• обычный текст;\n"
            "• фотографию с подписью или без неё;\n"
            "• видео с подписью или без неё.\n\n"
            "После этого вы сможете выбрать канал "
            "и посмотреть предпросмотр."
        ),
        reply_markup=get_post_content_keyboard(),
    )


@router.message(
    CreatePost.waiting_for_content,
    F.text == "❌ Отменить создание поста",
)
async def handle_create_post_cancel_message(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()

    await message.answer(
        text="Создание поста отменено.",
        reply_markup=get_main_menu(),
    )


@router.message(CreatePost.waiting_for_content)
async def handle_post_content(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        await state.clear()

        await message.answer(
            text="Не удалось определить пользователя.",
            reply_markup=get_main_menu(),
        )
        return

    content = extract_content(message)

    if content is None:
        await message.answer(
            text=(
                "Этот тип сообщения пока не поддерживается.\n\n"
                "Отправьте текст, фотографию или видео."
            ),
        )
        return

    content_type, text, telegram_file_id = content

    validation_error = validate_content(
        content_type=content_type,
        text=text,
    )

    if validation_error:
        await message.answer(validation_error)
        return

    channels = await get_owner_channels(
        owner_telegram_id=message.from_user.id,
    )

    if not channels:
        await state.clear()

        await message.answer(
            text=(
                "❌ Подключённые каналы не найдены.\n\n"
                "Добавьте канал в настройках."
            ),
            reply_markup=get_main_menu(),
        )
        return

    await state.update_data(
        content_type=content_type,
        text=text,
        telegram_file_id=telegram_file_id,
    )

    await state.set_state(
        CreatePost.waiting_for_channel,
    )

    await message.answer(
        text="Содержимое поста сохранено.",
        reply_markup=ReplyKeyboardRemove(),
    )

    await message.answer(
        text=(
            "📢 <b>Выберите канал</b>\n\n"
            "Куда нужно опубликовать этот пост?"
        ),
        reply_markup=get_post_channel_keyboard(
            channels,
        ),
    )


@router.callback_query(
    CreatePost.waiting_for_channel,
    F.data.startswith("post:channel:"),
)
async def handle_post_channel_selection(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    raw_callback_data = callback.data or ""

    try:
        channel_id = int(
            raw_callback_data.rsplit(
                ":",
                maxsplit=1,
            )[1]
        )
    except (IndexError, ValueError):
        await callback.answer(
            text="Некорректный идентификатор канала.",
            show_alert=True,
        )
        return

    channel = await get_owner_channel(
        channel_id=channel_id,
        owner_telegram_id=callback.from_user.id,
    )

    if channel is None:
        await callback.answer(
            text="Канал не найден или был отключён.",
            show_alert=True,
        )
        return

    data = await state.get_data()

    content_type = data.get("content_type")
    text = data.get("text")
    telegram_file_id = data.get(
        "telegram_file_id"
    )

    valid_content_types = {
        content_type_item.value
        for content_type_item in PublicationContentType
    }

    if (
        not isinstance(content_type, str)
        or content_type not in valid_content_types
        or (
            text is not None
            and not isinstance(text, str)
        )
        or (
            telegram_file_id is not None
            and not isinstance(
                telegram_file_id,
                str,
            )
        )
    ):
        await state.clear()

        await callback.message.answer(
            text=(
                "❌ Данные публикации повреждены.\n"
                "Начните создание поста заново."
            ),
            reply_markup=get_main_menu(),
        )

        await callback.answer()
        return

    async with SessionFactory() as session:
        publication_repository = (
            PublicationRepository(session)
        )

        publication = (
            await publication_repository.create_draft(
                owner_telegram_id=callback.from_user.id,
                channel_id=channel.id,
                content_type=content_type,
                text=text,
                telegram_file_id=telegram_file_id,
            )
        )

    await state.update_data(
        channel_id=channel.id,
        publication_id=publication.id,
    )

    await state.set_state(
        CreatePost.waiting_for_confirmation,
    )

    await callback.message.edit_text(
        text=(
            "🔎 <b>Предпросмотр публикации</b>\n\n"
            f"Канал: <b>{escape(channel.title)}</b>\n\n"
            "Ниже показан пост в том виде, "
            "в котором он будет опубликован."
        ),
    )

    try:
        await send_preview(
            message=callback.message,
            content_type=content_type,
            text=text,
            telegram_file_id=telegram_file_id,
        )
    except (TelegramAPIError, ValueError) as error:
        await mark_publication_failed(
            publication_id=publication.id,
            owner_telegram_id=callback.from_user.id,
            error_text=str(error),
        )

        await state.clear()

        await callback.message.answer(
            text=(
                "❌ Не удалось создать предпросмотр.\n\n"
                f"Причина: "
                f"<code>{escape(str(error))}</code>"
            ),
            reply_markup=get_main_menu(),
        )

    await callback.answer()


@router.callback_query(
    CreatePost.waiting_for_confirmation,
    F.data == "post:publish",
)
async def handle_post_publish(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()

    publication_id = data.get("publication_id")
    channel_id = data.get("channel_id")
    content_type = data.get("content_type")
    text = data.get("text")
    telegram_file_id = data.get(
        "telegram_file_id"
    )

    if (
        not isinstance(publication_id, int)
        or not isinstance(channel_id, int)
        or not isinstance(content_type, str)
        or (
            text is not None
            and not isinstance(text, str)
        )
        or (
            telegram_file_id is not None
            and not isinstance(
                telegram_file_id,
                str,
            )
        )
    ):
        await state.clear()

        await callback.message.answer(
            text=(
                "❌ Данные публикации повреждены.\n"
                "Начните создание поста заново."
            ),
            reply_markup=get_main_menu(),
        )

        await callback.answer()
        return

    channel = await get_owner_channel(
        channel_id=channel_id,
        owner_telegram_id=callback.from_user.id,
    )

    if channel is None:
        await state.clear()

        await callback.message.answer(
            text="❌ Выбранный канал больше недоступен.",
            reply_markup=get_main_menu(),
        )

        await callback.answer()
        return

    async with SessionFactory() as session:
        publication_repository = (
            PublicationRepository(session)
        )

        publication = (
            await publication_repository.get_by_id(
                publication_id=publication_id,
                owner_telegram_id=callback.from_user.id,
            )
        )

        if publication is None:
            await state.clear()

            await callback.message.answer(
                text=(
                    "❌ Публикация не найдена.\n"
                    "Начните создание поста заново."
                ),
                reply_markup=get_main_menu(),
            )

            await callback.answer()
            return

        if (
            publication.status
            == PublicationStatus.PUBLISHED.value
        ):
            await callback.answer(
                text="Пост уже опубликован.",
                show_alert=True,
            )
            return

        if (
            publication.status
            == PublicationStatus.PUBLISHING.value
        ):
            await callback.answer(
                text="Публикация уже выполняется.",
                show_alert=True,
            )
            return

        await publication_repository.mark_publishing(
            publication
        )

    try:
        published_message = await send_publication(
            bot=bot,
            chat_id=channel.telegram_chat_id,
            content_type=content_type,
            text=text,
            telegram_file_id=telegram_file_id,
        )

    except TelegramForbiddenError as error:
        await mark_publication_failed(
            publication_id=publication_id,
            owner_telegram_id=callback.from_user.id,
            error_text=str(error),
        )

        await callback.message.answer(
            text=(
                "❌ Telegram запретил публикацию.\n\n"
                "Проверьте, что бот всё ещё является "
                "администратором канала и имеет право "
                "публиковать сообщения."
            ),
        )

        await callback.answer(
            text="Не удалось опубликовать",
            show_alert=True,
        )
        return

    except TelegramBadRequest as error:
        await mark_publication_failed(
            publication_id=publication_id,
            owner_telegram_id=callback.from_user.id,
            error_text=str(error),
        )

        await callback.message.answer(
            text=(
                "❌ Telegram отклонил публикацию.\n\n"
                f"Причина: "
                f"<code>{escape(str(error))}</code>\n\n"
                "Можно исправить проблему или повторить "
                "публикацию."
            ),
        )

        await callback.answer(
            text="Ошибка публикации",
            show_alert=True,
        )
        return

    except (TelegramAPIError, ValueError) as error:
        await mark_publication_failed(
            publication_id=publication_id,
            owner_telegram_id=callback.from_user.id,
            error_text=str(error),
        )

        await callback.message.answer(
            text=(
                "❌ Не удалось опубликовать пост.\n\n"
                f"Причина: "
                f"<code>{escape(str(error))}</code>"
            ),
        )

        await callback.answer(
            text="Ошибка публикации",
            show_alert=True,
        )
        return

    async with SessionFactory() as session:
        publication_repository = (
            PublicationRepository(session)
        )

        publication = (
            await publication_repository.get_by_id(
                publication_id=publication_id,
                owner_telegram_id=callback.from_user.id,
            )
        )

        if publication is not None:
            await publication_repository.mark_published(
                publication,
                telegram_message_id=(
                    published_message.message_id
                ),
            )

    await state.clear()

    await callback.message.edit_reply_markup(
        reply_markup=None,
    )

    result_text = (
        "✅ <b>Пост опубликован</b>\n\n"
        f"Канал: <b>{escape(channel.title)}</b>\n"
        f"ID публикации: "
        f"<code>{publication_id}</code>\n"
        f"ID сообщения: "
        f"<code>{published_message.message_id}</code>"
    )

    if channel.username:
        post_url = (
            f"https://t.me/{channel.username}/"
            f"{published_message.message_id}"
        )

        result_text += (
            f'\n\n<a href="{post_url}">'
            "Открыть публикацию"
            "</a>"
        )

    await callback.message.answer(
        text=result_text,
        reply_markup=get_main_menu(),
    )

    await callback.answer(
        text="Пост опубликован",
    )


@router.callback_query(F.data == "post:cancel")
async def handle_create_post_cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    publication_id = data.get("publication_id")

    if isinstance(publication_id, int):
        async with SessionFactory() as session:
            publication_repository = (
                PublicationRepository(session)
            )

            publication = (
                await publication_repository.get_by_id(
                    publication_id=publication_id,
                    owner_telegram_id=(
                        callback.from_user.id
                    ),
                )
            )

            if (
                publication is not None
                and publication.status
                != PublicationStatus.PUBLISHED.value
            ):
                await (
                    publication_repository.mark_cancelled(
                        publication
                    )
                )

    await state.clear()

    if callback.message is not None:
        await callback.message.edit_reply_markup(
            reply_markup=None,
        )

        await callback.message.answer(
            text="Создание поста отменено.",
            reply_markup=get_main_menu(),
        )

    await callback.answer()