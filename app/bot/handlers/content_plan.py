from datetime import UTC, datetime
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.content_plan import (
    get_back_to_plan_keyboard,
    get_cancel_confirmation_keyboard,
    get_content_plan_keyboard,
    get_publication_actions_keyboard,
)
from app.config import get_settings
from app.database.models import (
    Channel,
    Publication,
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

router = Router(name=__name__)

CONTENT_TYPE_LABELS = {
    PublicationContentType.TEXT.value: "?????",
    PublicationContentType.PHOTO.value: "??????????",
    PublicationContentType.VIDEO.value: "?????",
}


def parse_publication_id(
    callback_data: str | None,
) -> int | None:
    if callback_data is None:
        return None

    try:
        return int(callback_data.rsplit(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        return None


def get_application_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)


def to_local_datetime(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(get_application_timezone())


def format_scheduled_at(
    value: datetime | None,
    *,
    include_year: bool,
) -> str:
    local_value = to_local_datetime(value)

    if local_value is None:
        return "????? ?? ???????"

    if include_year:
        return local_value.strftime("%d.%m.%Y %H:%M")

    return local_value.strftime("%d.%m %H:%M")


def format_content_preview(
    publication: Publication,
    *,
    limit: int = 700,
) -> str:
    if not publication.text:
        return "??? ??????"

    preview = publication.text.strip()

    if len(preview) > limit:
        preview = f"{preview[: limit - 1]}?"

    return preview


async def list_scheduled_items(
    *,
    owner_telegram_id: int,
) -> list[tuple[Publication, Channel | None]]:
    async with SessionFactory() as session:
        publication_repository = PublicationRepository(session)
        channel_repository = ChannelRepository(session)

        publications = await publication_repository.list_scheduled_by_owner(
            owner_telegram_id=owner_telegram_id,
        )

        items: list[tuple[Publication, Channel | None]] = []

        for publication in publications:
            channel = await channel_repository.get_by_id(
                channel_id=publication.channel_id,
                owner_telegram_id=owner_telegram_id,
            )
            items.append((publication, channel))

        return items


async def get_publication_item(
    *,
    publication_id: int,
    owner_telegram_id: int,
) -> tuple[Publication, Channel | None] | None:
    async with SessionFactory() as session:
        publication_repository = PublicationRepository(session)
        channel_repository = ChannelRepository(session)

        publication = await publication_repository.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )

        if publication is None:
            return None

        channel = await channel_repository.get_by_id(
            channel_id=publication.channel_id,
            owner_telegram_id=owner_telegram_id,
        )

        return publication, channel


def build_plan_view(
    items: list[tuple[Publication, Channel | None]],
) -> tuple[str, list[tuple[int, str]]]:
    if not items:
        return (
            "?? <b>???????-????</b>\n\n??????????????? ?????????? ???? ???.",
            [],
        )

    lines = [
        "?? <b>???????-????</b>",
        "",
        "????????? ??????????????? ??????????:",
        "",
    ]
    buttons: list[tuple[int, str]] = []

    for number, (publication, channel) in enumerate(
        items,
        start=1,
    ):
        scheduled_at = format_scheduled_at(
            publication.scheduled_at,
            include_year=False,
        )
        channel_title = channel.title if channel is not None else "????? ??????????"
        content_type = CONTENT_TYPE_LABELS.get(
            publication.content_type,
            publication.content_type,
        )

        lines.append(
            f"{number}. <b>{escape(scheduled_at)}</b> ? "
            f"{escape(channel_title)}\n"
            f"   {escape(content_type)} ? "
            f"?????????? #{publication.id}"
        )

        short_title = channel_title

        if len(short_title) > 24:
            short_title = f"{short_title[:21]}..."

        buttons.append(
            (
                publication.id,
                f"?? {scheduled_at} ? {short_title}",
            )
        )

    return "\n".join(lines), buttons


def build_publication_details(
    publication: Publication,
    channel: Channel | None,
) -> str:
    channel_title = channel.title if channel is not None else "????? ??????????"
    content_type = CONTENT_TYPE_LABELS.get(
        publication.content_type,
        publication.content_type,
    )
    scheduled_at = format_scheduled_at(
        publication.scheduled_at,
        include_year=True,
    )
    preview = format_content_preview(publication)

    return (
        "?? <b>??????????????? ??????????</b>\n\n"
        f"ID: <code>{publication.id}</code>\n"
        f"?????: <b>{escape(channel_title)}</b>\n"
        f"??????: {escape(content_type)}\n"
        f"???? ? ?????: <b>{escape(scheduled_at)}</b>\n\n"
        "<b>??????????:</b>\n"
        f"{escape(preview)}"
    )


@router.message(F.text == "?? ???????-????")
async def handle_content_plan(
    message: Message,
) -> None:
    if message.from_user is None:
        await message.answer("?? ??????? ?????????? ????????????.")
        return

    try:
        items = await list_scheduled_items(
            owner_telegram_id=message.from_user.id,
        )
        text, buttons = build_plan_view(items)
    except ZoneInfoNotFoundError:
        await message.answer(
            text=(
                "? ?? ??????? ??????? ???????-????: "
                "? APP_TIMEZONE ?????? ??????????? "
                "??????? ????."
            ),
        )
        return

    await message.answer(
        text=text,
        reply_markup=get_content_plan_keyboard(buttons),
    )


@router.callback_query(F.data == "plan:list")
async def handle_content_plan_list(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        items = await list_scheduled_items(
            owner_telegram_id=callback.from_user.id,
        )
        text, buttons = build_plan_view(items)
    except ZoneInfoNotFoundError:
        await callback.answer(
            text="???????????? APP_TIMEZONE",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        text=text,
        reply_markup=get_content_plan_keyboard(buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("plan:view:"))
async def handle_publication_details(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    publication_id = parse_publication_id(callback.data)

    if publication_id is None:
        await callback.answer(
            text="???????????? ID ??????????.",
            show_alert=True,
        )
        return

    item = await get_publication_item(
        publication_id=publication_id,
        owner_telegram_id=callback.from_user.id,
    )

    if item is None:
        await callback.answer(
            text="?????????? ?? ???????.",
            show_alert=True,
        )
        return

    publication, channel = item

    if publication.status != PublicationStatus.SCHEDULED.value:
        await callback.answer(
            text=("?????????? ??? ?? ????????? ? ???????."),
            show_alert=True,
        )
        return

    try:
        text = build_publication_details(
            publication,
            channel,
        )
    except ZoneInfoNotFoundError:
        await callback.answer(
            text="???????????? APP_TIMEZONE",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        text=text,
        reply_markup=get_publication_actions_keyboard(
            publication.id,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("plan:preview:"))
async def handle_publication_preview(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    publication_id = parse_publication_id(callback.data)

    if publication_id is None:
        await callback.answer(
            text="???????????? ID ??????????.",
            show_alert=True,
        )
        return

    item = await get_publication_item(
        publication_id=publication_id,
        owner_telegram_id=callback.from_user.id,
    )

    if item is None:
        await callback.answer(
            text="?????????? ?? ???????.",
            show_alert=True,
        )
        return

    publication, _ = item

    if publication.status != PublicationStatus.SCHEDULED.value:
        await callback.answer(
            text=("?????????? ??? ?? ????????? ? ???????."),
            show_alert=True,
        )
        return

    try:
        if publication.content_type == PublicationContentType.TEXT.value:
            if not publication.text:
                raise ValueError("? ????????? ?????????? ??????????? ?????.")

            await callback.message.answer(
                text=publication.text,
                parse_mode=None,
            )

        elif publication.content_type == PublicationContentType.PHOTO.value:
            if not publication.telegram_file_id:
                raise ValueError("? ?????????? ??????????? ??????????.")

            await callback.message.answer_photo(
                photo=publication.telegram_file_id,
                caption=publication.text or None,
                parse_mode=None,
            )

        elif publication.content_type == PublicationContentType.VIDEO.value:
            if not publication.telegram_file_id:
                raise ValueError("? ?????????? ??????????? ?????.")

            await callback.message.answer_video(
                video=publication.telegram_file_id,
                caption=publication.text or None,
                parse_mode=None,
                supports_streaming=True,
            )

        else:
            raise ValueError("??????????? ??? ??????????.")

    except (TelegramAPIError, ValueError) as error:
        await callback.answer(
            text="?? ??????? ???????? ????????????.",
            show_alert=True,
        )
        await callback.message.answer(
            text=(f"? ?????? ?????????????:\n<code>{escape(str(error)[:500])}</code>"),
        )
        return

    await callback.answer(
        text="???????????? ?????????.",
    )


@router.callback_query(F.data.startswith("plan:cancel:"))
async def handle_publication_cancel_request(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    publication_id = parse_publication_id(callback.data)

    if publication_id is None:
        await callback.answer(
            text="???????????? ID ??????????.",
            show_alert=True,
        )
        return

    item = await get_publication_item(
        publication_id=publication_id,
        owner_telegram_id=callback.from_user.id,
    )

    if item is None:
        await callback.answer(
            text="?????????? ?? ???????.",
            show_alert=True,
        )
        return

    publication, channel = item

    if publication.status != PublicationStatus.SCHEDULED.value:
        await callback.answer(
            text="??? ?????????? ??? ?????? ????????.",
            show_alert=True,
        )
        return

    channel_title = channel.title if channel is not None else "????? ??????????"

    await callback.message.edit_text(
        text=(
            "?? <b>???????? ???????????</b>\n\n"
            f"??????????: <code>{publication.id}</code>\n"
            f"?????: <b>{escape(channel_title)}</b>\n\n"
            "????? ?????? ???? ?? ????? ???????????."
        ),
        reply_markup=get_cancel_confirmation_keyboard(
            publication.id,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("plan:cancel_confirm:"))
async def handle_publication_cancel_confirm(
    callback: CallbackQuery,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    publication_id = parse_publication_id(callback.data)

    if publication_id is None:
        await callback.answer(
            text="???????????? ID ??????????.",
            show_alert=True,
        )
        return

    async with SessionFactory() as session:
        repository = PublicationRepository(session)

        publication = await repository.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=callback.from_user.id,
        )

        if publication is None:
            await callback.answer(
                text="?????????? ?? ???????.",
                show_alert=True,
            )
            return

        if publication.status != PublicationStatus.SCHEDULED.value:
            await callback.answer(
                text=("?????????? ??? ?????????????? ??? ???? ????????."),
                show_alert=True,
            )
            return

        await repository.mark_cancelled(publication)

    await callback.message.edit_text(
        text=(
            "? <b>?????????? ????????</b>\n\n"
            f"???? #{publication_id} ?????? "
            "?? ??????? ? ??????????? ?? ?????."
        ),
        reply_markup=get_back_to_plan_keyboard(),
    )
    await callback.answer(
        text="?????????? ????????.",
    )
