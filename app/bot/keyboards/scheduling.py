from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)


def get_schedule_web_app_keyboard(
    *,
    mini_app_url: str,
) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📅 Выбрать дату и время",
                    web_app=WebAppInfo(
                        url=mini_app_url,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    text="❌ Отменить создание поста",
                ),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder=("Откройте календарь кнопкой ниже"),
    )
