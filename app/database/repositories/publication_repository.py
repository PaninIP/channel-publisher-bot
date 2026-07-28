from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Publication,
    PublicationStatus,
)


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
            Publication.owner_telegram_id
            == owner_telegram_id,
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def mark_publishing(
        self,
        publication: Publication,
    ) -> None:
        publication.status = (
            PublicationStatus.PUBLISHING.value
        )
        publication.error_text = None

        await self.session.commit()

    async def mark_published(
        self,
        publication: Publication,
        *,
        telegram_message_id: int,
    ) -> None:
        publication.status = (
            PublicationStatus.PUBLISHED.value
        )
        publication.telegram_message_id = (
            telegram_message_id
        )
        publication.published_at = datetime.now(UTC)
        publication.error_text = None

        await self.session.commit()

    async def mark_failed(
        self,
        publication: Publication,
        *,
        error_text: str,
    ) -> None:
        publication.status = (
            PublicationStatus.FAILED.value
        )
        publication.error_text = error_text[:2000]

        await self.session.commit()

    async def mark_cancelled(
        self,
        publication: Publication,
    ) -> None:
        publication.status = (
            PublicationStatus.CANCELLED.value
        )

        await self.session.commit()