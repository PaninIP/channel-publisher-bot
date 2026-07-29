import json
from datetime import UTC, datetime, timedelta
from html import escape
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

router = Router(name=__name__)


def get_timezone_name() -> str:
    return get_settings().app_timezone.strip()


def get_application_timezone() -> ZoneInfo:
    return ZoneInfo(get_timezone_name())


def build_mini_app_url() -> str:
    settings = get_settings()
    parsed_url = urlsplit(
        settings.mini_app_url.strip(),
    )

    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("MINI_APP_URL должен быть публичным HTTPS URL.")

    timezone = get_application_timezone()
    minimum_datetime = (datetime.now(timezone) + timedelta(minutes=2)).replace(
        second=0,
        microsecond=0,
    )

    query_items = dict(
        parse_qsl(
            parsed_url.query,
            keep_blank_values=True,
        )
    )
    query_items.update(
        {
            "timezone": get_timezone_name(),
            "min_local": minimum_datetime.strftime(
                "%Y-%m-%dT%H:%M",
            ),
        }
    )

    return urlunsplit(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path or "/",
            urlencode(query_items),
            parsed_url.fragment,
        )
    )


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
    except (ValueError, ZoneInfoNotFoundError) as error:
        await callback.answer(
            text="Mini App пока не настроен.",
            show_alert=True,
        )
        await callback.message.answer(
            text=(
                "❌ <b>Не удалось открыть календарь</b>\n\n"
                f"<code>{escape(str(error))}</code>\n\n"
                "Проверьте MINI_APP_URL и APP_TIMEZONE "
                "в файле .env."
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
            f"Часовой пояс: "
            f"<code>{escape(get_timezone_name())}</code>"
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

    if (
        action != "schedule_publication"
        or not isinstance(scheduled_local, str)
        or not isinstance(timezone_name, str)
    ):
        await message.answer(
            text="❌ Mini App передал неполные данные.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    configured_timezone_name = get_timezone_name()

    if timezone_name.strip() != configured_timezone_name:
        await message.answer(
            text=("❌ Часовой пояс Mini App не совпадает с настройками бота."),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    try:
        timezone = get_application_timezone()
        selected_naive = datetime.fromisoformat(
            scheduled_local,
        )

        if selected_naive.tzinfo is not None:
            selected_naive = selected_naive.replace(
                tzinfo=None,
            )

        selected_local = selected_naive.replace(
            tzinfo=timezone,
        )
    except (ValueError, ZoneInfoNotFoundError):
        await message.answer(
            text="❌ Не удалось распознать дату и время.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if selected_local <= (datetime.now(timezone) + timedelta(minutes=1)):
        await message.answer(
            text=(
                "❌ Выбранное время уже прошло.\n"
                "Откройте календарь и выберите "
                "более позднее время."
            ),
            reply_markup=get_schedule_web_app_keyboard(
                mini_app_url=build_mini_app_url(),
            ),
        )
        return

    data = await state.get_data()
    publication_id = data.get("publication_id")

    if not isinstance(publication_id, int):
        await state.clear()
        await message.answer(
            text=("❌ Не удалось получить публикацию.\nНачните создание поста заново."),
            reply_markup=get_main_menu(),
        )
        return

    scheduled_utc = selected_local.astimezone(UTC).replace(tzinfo=None)

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

        if publication.status == PublicationStatus.PUBLISHED.value:
            await state.clear()
            await message.answer(
                text="Публикация уже была отправлена.",
                reply_markup=get_main_menu(),
            )
            return

        await repository.schedule(
            publication,
            scheduled_at_utc=scheduled_utc,
        )

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
            f"Часовой пояс: "
            f"<code>{escape(configured_timezone_name)}</code>"
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
