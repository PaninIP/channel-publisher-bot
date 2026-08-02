from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Publication,
    PublicationStatus,
)


def utc_now_naive() -> datetime:
    """?????????? ??????? UTC-????? ??? tzinfo ??? SQLite."""
    return datetime.now(UTC).replace(tzinfo=None)


class PublicationRepository:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def create_draft(
        self,
        *,
        owner_telegram_id: int,
        channel_id: int,
        content_type: str,
        text: str | None,
        telegram_file_id: str | None,
    ) -> Publication:
        publication = Publication(
            owner_telegram_id=owner_telegram_id,
            channel_id=channel_id,
            content_type=content_type,
            text=text,
            telegram_file_id=telegram_file_id,
            status=PublicationStatus.DRAFT.value,
        )

        self.session.add(publication)

        await self.session.commit()
        await self.session.refresh(publication)

        return publication

    async def get_by_id(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
    ) -> Publication | None:
        statement = select(Publication).where(
            Publication.id == publication_id,
            Publication.owner_telegram_id == owner_telegram_id,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def list_scheduled_by_owner(
        self,
        *,
        owner_telegram_id: int,
        limit: int = 20,
    ) -> list[Publication]:
        statement = (
            select(Publication)
            .where(
                Publication.owner_telegram_id == owner_telegram_id,
                Publication.status == PublicationStatus.SCHEDULED.value,
                Publication.scheduled_at.is_not(None),
            )
            .order_by(
                Publication.scheduled_at,
                Publication.id,
            )
            .limit(limit)
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def list_scheduled_for_period(
        self,
        *,
        owner_telegram_id: int,
        starts_at_utc: datetime,
        ends_at_utc: datetime,
        limit: int = 500,
    ) -> list[Publication]:
        statement = (
            select(Publication)
            .where(
                Publication.owner_telegram_id == owner_telegram_id,
                Publication.status == PublicationStatus.SCHEDULED.value,
                Publication.scheduled_at.is_not(None),
                Publication.scheduled_at >= starts_at_utc,
                Publication.scheduled_at < ends_at_utc,
            )
            .order_by(
                Publication.scheduled_at,
                Publication.id,
            )
            .limit(limit)
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def list_due_scheduled(
        self,
        *,
        limit: int = 20,
    ) -> list[Publication]:
        statement = (
            select(Publication)
            .where(
                Publication.status == PublicationStatus.SCHEDULED.value,
                Publication.scheduled_at.is_not(None),
                Publication.scheduled_at <= utc_now_naive(),
            )
            .order_by(
                Publication.scheduled_at,
                Publication.id,
            )
            .limit(limit)
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def schedule(
        self,
        publication: Publication,
        *,
        scheduled_at_utc: datetime,
    ) -> None:
        publication.status = PublicationStatus.SCHEDULED.value
        publication.scheduled_at = scheduled_at_utc
        publication.error_text = None

        await self.session.commit()

    async def update_scheduled(
        self,
        publication: Publication,
        *,
        channel_id: int,
        text: str | None,
        scheduled_at_utc: datetime,
    ) -> None:
        publication.channel_id = channel_id
        publication.text = text
        publication.scheduled_at = scheduled_at_utc
        publication.error_text = None

        await self.session.commit()
        await self.session.refresh(publication)

    async def mark_publishing(
        self,
        publication: Publication,
    ) -> None:
        publication.status = PublicationStatus.PUBLISHING.value
        publication.error_text = None

        await self.session.commit()

    async def mark_published(
        self,
        publication: Publication,
        *,
        telegram_message_id: int,
    ) -> None:
        publication.status = PublicationStatus.PUBLISHED.value
        publication.telegram_message_id = telegram_message_id
        publication.published_at = utc_now_naive()
        publication.error_text = None

        await self.session.commit()

    async def mark_failed(
        self,
        publication: Publication,
        *,
        error_text: str,
    ) -> None:
        publication.status = PublicationStatus.FAILED.value
        publication.error_text = error_text[:2000]

        await self.session.commit()

    async def mark_cancelled(
        self,
        publication: Publication,
    ) -> None:
        publication.status = PublicationStatus.CANCELLED.value

        await self.session.commit()
