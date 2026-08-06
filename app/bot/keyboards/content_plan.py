from collections.abc import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_content_plan_web_app_keyboard(
    *,
    mini_app_url: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Открыть контент-план",
                    web_app=WebAppInfo(
                        url=mini_app_url,
                    ),
                ),
            ],
        ],
    )


def get_content_plan_keyboard(
    items: Sequence[tuple[int, str]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for publication_id, button_text in items:
        builder.button(
            text=button_text,
            callback_data=f"plan:view:{publication_id}",
        )

    builder.button(
        text="🔄 Обновить",
        callback_data="plan:list",
    )
    builder.adjust(1)

    return builder.as_markup()


def get_publication_actions_keyboard(
    publication_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👁 Предпросмотр",
                    callback_data=f"plan:preview:{publication_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить публикацию",
                    callback_data=f"plan:cancel:{publication_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ В контент-план",
                    callback_data="plan:list",
                ),
            ],
        ],
    )


def get_cancel_confirmation_keyboard(
    publication_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, отменить",
                    callback_data=(f"plan:cancel_confirm:{publication_id}"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Нет, вернуться",
                    callback_data=f"plan:view:{publication_id}",
                ),
            ],
        ],
    )


def get_back_to_plan_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ В контент-план",
                    callback_data="plan:list",
                ),
            ],
        ],
    )
