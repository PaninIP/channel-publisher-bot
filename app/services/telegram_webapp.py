import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl


class TelegramWebAppAuthError(ValueError):
    pass


def validate_telegram_init_data(
    init_data: str,
    *,
    bot_token: str,
    max_age_seconds: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not init_data:
        raise TelegramWebAppAuthError("Telegram initData отсутствует.")

    parsed_items = dict(
        parse_qsl(
            init_data,
            keep_blank_values=True,
        )
    )

    received_hash = parsed_items.pop(
        "hash",
        None,
    )

    if not received_hash:
        raise TelegramWebAppAuthError("В initData отсутствует hash.")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(parsed_items.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        calculated_hash,
        received_hash,
    ):
        raise TelegramWebAppAuthError("Подпись initData не прошла проверку.")

    try:
        auth_date = int(parsed_items["auth_date"])
    except (KeyError, TypeError, ValueError) as error:
        raise TelegramWebAppAuthError("Некорректный auth_date.") from error

    current_time = now or datetime.now(UTC)

    if current_time.tzinfo is None:
        current_time = current_time.replace(
            tzinfo=UTC,
        )

    current_timestamp = int(current_time.timestamp())

    if auth_date > current_timestamp + 30:
        raise TelegramWebAppAuthError("auth_date находится в будущем.")

    if current_timestamp - auth_date > max_age_seconds:
        raise TelegramWebAppAuthError("Срок действия initData истёк.")

    try:
        user = json.loads(parsed_items["user"])
    except (
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as error:
        raise TelegramWebAppAuthError("В initData отсутствует пользователь.") from error

    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise TelegramWebAppAuthError("Некорректные данные пользователя.")

    return user
