import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest

from app.services.telegram_webapp import (
    TelegramWebAppAuthError,
    validate_telegram_init_data,
)

BOT_TOKEN = "123456:TEST_TOKEN"


def build_init_data(
    *,
    user_id: int = 42,
    auth_date: datetime,
) -> str:
    fields = {
        "auth_date": str(int(auth_date.timestamp())),
        "query_id": "test-query-id",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Test",
            },
            separators=(",", ":"),
        ),
    }

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )

    secret_key = hmac.new(
        b"WebAppData",
        BOT_TOKEN.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    fields["hash"] = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return urlencode(fields)


def test_valid_init_data_returns_user() -> None:
    now = datetime.now(UTC)
    init_data = build_init_data(
        auth_date=now,
    )

    user = validate_telegram_init_data(
        init_data,
        bot_token=BOT_TOKEN,
        max_age_seconds=3600,
        now=now,
    )

    assert user["id"] == 42


def test_tampered_init_data_is_rejected() -> None:
    now = datetime.now(UTC)
    init_data = build_init_data(
        auth_date=now,
    ).replace(
        "test-query-id",
        "tampered-query-id",
    )

    with pytest.raises(
        TelegramWebAppAuthError,
    ):
        validate_telegram_init_data(
            init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=3600,
            now=now,
        )


def test_expired_init_data_is_rejected() -> None:
    now = datetime.now(UTC)
    init_data = build_init_data(
        auth_date=(now - timedelta(hours=2)),
    )

    with pytest.raises(
        TelegramWebAppAuthError,
    ):
        validate_telegram_init_data(
            init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=3600,
            now=now,
        )
