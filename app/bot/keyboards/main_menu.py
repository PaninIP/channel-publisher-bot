from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📝 Создать пост"),
                KeyboardButton(text="📅 Контент-план"),
            ],
            [
                KeyboardButton(text="✏️ Изменить пост"),
                KeyboardButton(text="📊 Статистика"),
            ],
            [
                KeyboardButton(text="🤖 Нейропостинг"),
                KeyboardButton(text="⚙️ Настройки"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел",
    )