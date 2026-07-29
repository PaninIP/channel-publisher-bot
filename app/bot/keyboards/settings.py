from aiogram.types import (
    ChatAdministratorRights,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    ReplyKeyboardMarkup,
)

CHANNEL_REQUEST_ID = 1001


def get_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Каналы",
                    callback_data="settings:channels",
                ),
            ],
        ],
    )


def get_channels_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить канал",
                    callback_data="channels:add",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="channels:back",
                ),
            ],
        ],
    )


def get_channel_posting_rights() -> ChatAdministratorRights:
    return ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=False,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_post_messages=True,
        can_edit_messages=False,
        can_pin_messages=False,
        can_manage_topics=False,
        can_manage_direct_messages=False,
        can_manage_tags=False,
    )


def get_channel_selector_keyboard() -> ReplyKeyboardMarkup:
    required_rights = get_channel_posting_rights()

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📢 Выбрать канал",
                    request_chat=KeyboardButtonRequestChat(
                        request_id=CHANNEL_REQUEST_ID,
                        chat_is_channel=True,
                        user_administrator_rights=required_rights,
                        bot_administrator_rights=required_rights,
                        request_title=True,
                        request_username=True,
                        request_photo=False,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    text="❌ Отмена",
                ),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Выберите канал",
    )
