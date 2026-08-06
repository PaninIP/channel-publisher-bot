from types import SimpleNamespace

import pytest

pytest.importorskip("aiogram")

from app.config import Settings  # noqa: E402
from app.database.models import PublicationMedia  # noqa: E402
from app.services.publication_sender import send_publication  # noqa: E402


class FakeBot:
    def __init__(self) -> None:
        self.sent_media_group = None

    async def send_media_group(self, *, chat_id, media):
        self.sent_media_group = (chat_id, media)
        return [
            SimpleNamespace(
                message_id=100 + index,
                photo=[SimpleNamespace(file_id=f"photo-{index}")]
                if item.type == "photo"
                else None,
                video=SimpleNamespace(file_id=f"video-{index}")
                if item.type == "video"
                else None,
            )
            for index, item in enumerate(media)
        ]


@pytest.mark.asyncio
async def test_album_uses_caption_only_on_first_item() -> None:
    bot = FakeBot()
    media = [
        PublicationMedia(
            id=1,
            publication_id=10,
            owner_telegram_id=20,
            media_type="photo",
            storage_backend="telegram",
            telegram_file_id="existing-photo",
            position=1,
        ),
        PublicationMedia(
            id=2,
            publication_id=10,
            owner_telegram_id=20,
            media_type="video",
            storage_backend="telegram",
            telegram_file_id="existing-video",
            position=2,
        ),
    ]

    result = await send_publication(
        bot=bot,
        chat_id=-100123,
        content_type="album",
        text="Подпись альбома",
        telegram_file_id=None,
        media_items=media,
        settings=Settings(bot_token="test-token"),
        show_caption_above_media=True,
    )

    assert bot.sent_media_group is not None
    _, telegram_media = bot.sent_media_group
    assert telegram_media[0].caption == "Подпись альбома"
    assert telegram_media[0].show_caption_above_media is True
    assert telegram_media[1].caption is None
    assert telegram_media[1].show_caption_above_media is False
    assert result.message_ids == [100, 101]
    assert result.file_ids_by_media_id == {1: "photo-0", 2: "video-1"}
