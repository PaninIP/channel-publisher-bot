from datetime import timedelta

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.database.base import Base  # noqa: E402
from app.database.models import Publication, PublicationStatus  # noqa: E402
from app.database.repositories.publication_media_repository import (  # noqa: E402
    PublicationMediaConflictError,
    PublicationMediaRepository,
)
from app.database.repositories.publication_repository import utc_now_naive  # noqa: E402


async def create_scheduled_publication(
    session, *, text: str = "Подпись"
) -> Publication:
    publication = Publication(
        owner_telegram_id=101,
        channel_id=1,
        content_type="text",
        text=text,
        status=PublicationStatus.SCHEDULED.value,
        scheduled_at=utc_now_naive() + timedelta(hours=1),
        version=1,
    )
    session.add(publication)
    await session.commit()
    await session.refresh(publication)
    return publication


@pytest.mark.asyncio
async def test_add_reorder_options_and_remove_media() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            publication = await create_scheduled_publication(session)
            repository = PublicationMediaRepository(session)

            first = await repository.add_uploaded(
                publication_id=publication.id,
                owner_telegram_id=101,
                expected_version=1,
                media_type="photo",
                storage_backend="local",
                storage_key="one.jpg",
                original_filename="one.jpg",
                content_type="image/jpeg",
                file_size=100,
                max_items=10,
            )
            assert first.version == 2
            assert first.content_type == "photo"
            assert [item.position for item in first.media] == [1]

            second = await repository.add_uploaded(
                publication_id=publication.id,
                owner_telegram_id=101,
                expected_version=2,
                media_type="video",
                storage_backend="local",
                storage_key="two.mp4",
                original_filename="two.mp4",
                content_type="video/mp4",
                file_size=200,
                max_items=10,
            )
            assert second.version == 3
            assert second.content_type == "album"

            reordered = await repository.reorder(
                publication_id=publication.id,
                owner_telegram_id=101,
                expected_version=3,
                media_ids=[second.media[1].id, second.media[0].id],
            )
            assert reordered.version == 4
            assert [item.original_filename for item in reordered.media] == [
                "two.mp4",
                "one.jpg",
            ]

            options = await repository.set_options(
                publication_id=publication.id,
                owner_telegram_id=101,
                expected_version=4,
                media_id=reordered.media[0].id,
                has_spoiler=True,
                show_caption_above_media=True,
            )
            assert options.version == 5
            assert options.media[0].has_spoiler is True

            removed = await repository.remove(
                publication_id=publication.id,
                media_id=reordered.media[0].id,
                owner_telegram_id=101,
                expected_version=5,
            )
            assert removed.version == 6
            assert removed.content_type == "photo"
            assert len(removed.media) == 1
            assert removed.media[0].position == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_media_mutation_rejects_stale_version() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            publication = await create_scheduled_publication(session)
            repository = PublicationMediaRepository(session)
            await repository.add_uploaded(
                publication_id=publication.id,
                owner_telegram_id=101,
                expected_version=1,
                media_type="photo",
                storage_backend="local",
                storage_key="one.jpg",
                original_filename="one.jpg",
                content_type="image/jpeg",
                file_size=100,
                max_items=10,
            )

            with pytest.raises(PublicationMediaConflictError, match="Обновите"):
                await repository.add_uploaded(
                    publication_id=publication.id,
                    owner_telegram_id=101,
                    expected_version=1,
                    media_type="photo",
                    storage_backend="local",
                    storage_key="stale.jpg",
                    original_filename="stale.jpg",
                    content_type="image/jpeg",
                    file_size=100,
                    max_items=10,
                )
    finally:
        await engine.dispose()
