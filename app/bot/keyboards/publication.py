from collections.abc import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Channel


def get_post_content_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="❌ Отменить создание поста",
                ),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=("Отправьте текст, фото или видео"),
    )


def get_post_channel_keyboard(
    channels: Sequence[Channel],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for channel in channels:
        title = channel.title

        if len(title) > 40:
            title = f"{title[:37]}..."

        builder.button(
            text=f"📢 {title}",
            callback_data=f"post:channel:{channel.id}",
        )

    builder.button(
        text="❌ Отмена",
        callback_data="post:cancel",
    )

    builder.adjust(1)

    return builder.as_markup()


def get_post_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Опубликовать сейчас",
                    callback_data="post:publish",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🕒 Запланировать",
                    callback_data="post:schedule",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="post:cancel",
                ),
            ],
        ],
    )


def get_schedule_time_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="❌ Отменить создание поста",
                ),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Например: 29.07.2026 18:30",
    )
