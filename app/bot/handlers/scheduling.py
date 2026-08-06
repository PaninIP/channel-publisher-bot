import json
from datetime import datetime
from html import escape
from urllib.parse import urlsplit

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardRemove,
)

from app.bot.keyboards.main_menu import get_main_menu
from app.bot.keyboards.scheduling import (
    get_schedule_web_app_keyboard,
)
from app.bot.states.publication import CreatePost
from app.config import get_settings
from app.database.models import PublicationStatus
from app.database.repositories.publication_repository import (
    PublicationRepository,
)
from app.database.session import SessionFactory
from app.services.content_plan_editor import (
    ContentPlanEditorValidationError,
    parse_scheduled_local,
)

router = Router(name=__name__)


def build_mini_app_url() -> str:
    settings = get_settings()
    mini_app_url = settings.mini_app_url.strip()
    parsed_url = urlsplit(mini_app_url)

    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("MINI_APP_URL должен быть публичным HTTPS URL.")

    return mini_app_url


def format_timezone_label(
    timezone_name: str,
    timezone_offset_minutes: int | None,
) -> str:
    normalized_name = timezone_name.strip()

    if timezone_offset_minutes is None:
        return normalized_name or "Часовой пояс устройства"

    sign = "+" if timezone_offset_minutes >= 0 else "-"
    absolute_minutes = abs(timezone_offset_minutes)
    hours, minutes = divmod(absolute_minutes, 60)
    offset = f"UTC{sign}{hours:02d}:{minutes:02d}"
    if normalized_name:
        return f"{normalized_name} ({offset})"

    return offset


async def cancel_publication_from_state(
    *,
    state: FSMContext,
    owner_telegram_id: int,
) -> None:
    data = await state.get_data()
    publication_id = data.get("publication_id")

    if not isinstance(publication_id, int):
        return

    async with SessionFactory() as session:
        repository = PublicationRepository(session)

        publication = await repository.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )

        if (
            publication is not None
            and publication.status != PublicationStatus.PUBLISHED.value
        ):
            await repository.mark_cancelled(publication)


@router.callback_query(
    CreatePost.waiting_for_confirmation,
    F.data == "post:schedule",
)
async def handle_schedule_selection(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()
    publication_id = data.get("publication_id")

    if not isinstance(publication_id, int):
        await state.clear()
        await callback.message.answer(
            text=("❌ Не удалось получить публикацию.\nНачните создание поста заново."),
            reply_markup=get_main_menu(),
        )
        await callback.answer()
        return

    try:
        mini_app_url = build_mini_app_url()
    except ValueError as error:
        await callback.answer(
            text="Mini App пока не настроен.",
            show_alert=True,
        )
        await callback.message.answer(
            text=(
                "❌ <b>Не удалось открыть календарь</b>\n\n"
                f"<code>{escape(str(error))}</code>\n\n"
                "Проверьте MINI_APP_URL в файле .env."
            ),
            reply_markup=get_main_menu(),
        )
        return

    await state.set_state(
        CreatePost.waiting_for_schedule_time,
    )

    await callback.message.edit_reply_markup(
        reply_markup=None,
    )

    await callback.message.answer(
        text=(
            "📅 <b>Выберите дату и время</b>\n\n"
            "Нажмите кнопку ниже. Откроется "
            "системный календарь телефона.\n\n"
            "Часовой пояс определяется автоматически "
            "по настройкам устройства."
        ),
        reply_markup=get_schedule_web_app_keyboard(
            mini_app_url=mini_app_url,
        ),
    )

    await callback.answer()


@router.message(
    CreatePost.waiting_for_schedule_time,
    F.text == "❌ Отменить создание поста",
)
async def handle_schedule_cancel(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is not None:
        await cancel_publication_from_state(
            state=state,
            owner_telegram_id=message.from_user.id,
        )

    await state.clear()

    await message.answer(
        text="Создание поста отменено.",
        reply_markup=get_main_menu(),
    )


@router.message(
    CreatePost.waiting_for_schedule_time,
    F.web_app_data,
)
async def handle_schedule_web_app_data(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None or message.web_app_data is None:
        return

    try:
        payload = json.loads(
            message.web_app_data.data,
        )
    except json.JSONDecodeError:
        await message.answer(
            text="❌ Mini App передал некорректные данные.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if not isinstance(payload, dict):
        await message.answer(
            text="❌ Некорректный формат данных.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    action = payload.get("action")
    scheduled_local = payload.get("scheduled_local")
    timezone_name = payload.get("timezone")
    timezone_offset_minutes = payload.get("timezone_offset_minutes")

    if (
        action != "schedule_publication"
        or not isinstance(scheduled_local, str)
        or not isinstance(timezone_name, str)
        or isinstance(timezone_offset_minutes, bool)
        or (
            timezone_offset_minutes is not None
            and not isinstance(timezone_offset_minutes, int)
        )
    ):
        await message.answer(
            text="❌ Mini App передал неполные данные.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    try:
        scheduled_utc = parse_scheduled_local(
            scheduled_local,
            timezone_name=timezone_name,
            timezone_offset_minutes=timezone_offset_minutes,
        )
        selected_local = datetime.fromisoformat(scheduled_local)
    except ContentPlanEditorValidationError as error:
        await message.answer(
            text=f"❌ {escape(str(error))}",
            reply_markup=get_schedule_web_app_keyboard(
                mini_app_url=build_mini_app_url(),
            ),
        )
        return

    timezone_label = format_timezone_label(
        timezone_name,
        timezone_offset_minutes,
    )

    data = await state.get_data()
    publication_id = data.get("publication_id")

    if not isinstance(publication_id, int):
        await state.clear()
        await message.answer(
            text=("❌ Не удалось получить публикацию.\nНачните создание поста заново."),
            reply_markup=get_main_menu(),
        )
        return

    async with SessionFactory() as session:
        repository = PublicationRepository(session)

        publication = await repository.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=message.from_user.id,
        )

        if publication is None:
            await state.clear()
            await message.answer(
                text="❌ Публикация не найдена.",
                reply_markup=get_main_menu(),
            )
            return

        scheduled = await repository.schedule_if_draft(
            publication_id=publication.id,
            owner_telegram_id=message.from_user.id,
            scheduled_at_utc=scheduled_utc,
        )

        if not scheduled:
            await state.clear()
            await message.answer(
                text=("Публикация уже была отправлена, запланирована или отменена."),
                reply_markup=get_main_menu(),
            )
            return

    await state.clear()

    await message.answer(
        text=(
            "✅ <b>Публикация запланирована</b>\n\n"
            f"ID публикации: "
            f"<code>{publication_id}</code>\n"
            f"Дата: "
            f"<b>{selected_local:%d.%m.%Y}</b>\n"
            f"Время: "
            f"<b>{selected_local:%H:%M}</b>\n"
            f"Часовой пояс устройства: "
            f"<code>{escape(timezone_label)}</code>"
        ),
        reply_markup=get_main_menu(),
    )


@router.message(
    CreatePost.waiting_for_schedule_time,
)
async def handle_unexpected_schedule_message(
    message: Message,
) -> None:
    await message.answer(
        text=("Для выбора даты нажмите кнопку «📅 Выбрать дату и время»."),
    )
