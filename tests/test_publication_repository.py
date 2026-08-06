from datetime import datetime, timedelta

import pytest

pytest.importorskip("aiosqlite")

from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from app.database.base import Base  # noqa: E402
from app.database.models import (  # noqa: E402
    Publication,
    PublicationStatus,
)
from app.database.repositories.publication_repository import (  # noqa: E402
    PublicationRepository,
    utc_now_naive,
)


@pytest.mark.asyncio
async def test_only_first_claim_changes_scheduled_publication() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
        )

        async with session_factory() as session:
            publication = Publication(
                owner_telegram_id=10,
                channel_id=1,
                content_type="text",
                text="Тест",
                status=PublicationStatus.SCHEDULED.value,
                scheduled_at=utc_now_naive() - timedelta(minutes=1),
            )
            session.add(publication)
            await session.commit()
            await session.refresh(publication)
            publication_id = publication.id

        async with session_factory() as session:
            repository = PublicationRepository(session)
            first_claim = await repository.claim_for_publishing(
                publication_id=publication_id,
                owner_telegram_id=10,
                expected_status=PublicationStatus.SCHEDULED.value,
                require_due=True,
            )

        async with session_factory() as session:
            repository = PublicationRepository(session)
            second_claim = await repository.claim_for_publishing(
                publication_id=publication_id,
                owner_telegram_id=10,
                expected_status=PublicationStatus.SCHEDULED.value,
                require_due=True,
            )

        assert first_claim is not None
        assert first_claim.status == PublicationStatus.PUBLISHING.value
        assert first_claim.publishing_started_at is not None
        assert second_claim is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_publishing_is_marked_failed_without_retry() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
        )

        async with session_factory() as session:
            publication = Publication(
                owner_telegram_id=20,
                channel_id=1,
                content_type="text",
                text="Тест",
                status=PublicationStatus.PUBLISHING.value,
                publishing_started_at=(utc_now_naive() - timedelta(minutes=10)),
            )
            session.add(publication)
            await session.commit()
            await session.refresh(publication)
            publication_id = publication.id

        async with session_factory() as session:
            repository = PublicationRepository(session)
            recovered = await repository.recover_stale_publishing(
                stale_before_utc=(utc_now_naive() - timedelta(minutes=5)),
            )

        async with session_factory() as session:
            repository = PublicationRepository(session)
            publication = await repository.get_by_id(
                publication_id=publication_id,
                owner_telegram_id=20,
            )

        assert recovered == [(publication_id, 20)]
        assert publication is not None
        assert publication.status == PublicationStatus.FAILED.value
        assert publication.publishing_started_at is None
        assert "дубликата" in (publication.error_text or "")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_future_scheduled_publication_cannot_be_claimed_as_due() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
        )

        async with session_factory() as session:
            publication = Publication(
                owner_telegram_id=30,
                channel_id=1,
                content_type="text",
                text="Тест",
                status=PublicationStatus.SCHEDULED.value,
                scheduled_at=datetime.now() + timedelta(hours=1),
            )
            session.add(publication)
            await session.commit()
            await session.refresh(publication)
            publication_id = publication.id

        async with session_factory() as session:
            repository = PublicationRepository(session)
            claimed = await repository.claim_for_publishing(
                publication_id=publication_id,
                owner_telegram_id=30,
                expected_status=PublicationStatus.SCHEDULED.value,
                require_due=True,
            )

        assert claimed is None
    finally:
        await engine.dispose()
