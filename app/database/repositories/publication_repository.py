from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Publication,
    PublicationStatus,
)


def utc_now_naive() -> datetime:
    """Возвращает текущее UTC-время без tzinfo для совместимости с SQLite."""
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

    async def schedule_if_draft(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
        scheduled_at_utc: datetime,
    ) -> bool:
        statement = (
            update(Publication)
            .where(
                Publication.id == publication_id,
                Publication.owner_telegram_id == owner_telegram_id,
                Publication.status == PublicationStatus.DRAFT.value,
            )
            .values(
                status=PublicationStatus.SCHEDULED.value,
                scheduled_at=scheduled_at_utc,
                error_text=None,
                publishing_started_at=None,
            )
        )

        result = await self.session.execute(statement)
        await self.session.commit()

        return result.rowcount == 1

    async def schedule(
        self,
        publication: Publication,
        *,
        scheduled_at_utc: datetime,
    ) -> bool:
        return await self.schedule_if_draft(
            publication_id=publication.id,
            owner_telegram_id=publication.owner_telegram_id,
            scheduled_at_utc=scheduled_at_utc,
        )

    async def update_scheduled(
        self,
        publication: Publication,
        *,
        channel_id: int,
        text: str | None,
        scheduled_at_utc: datetime,
    ) -> bool:
        statement = (
            update(Publication)
            .where(
                Publication.id == publication.id,
                Publication.owner_telegram_id == publication.owner_telegram_id,
                Publication.status == PublicationStatus.SCHEDULED.value,
            )
            .values(
                channel_id=channel_id,
                text=text,
                scheduled_at=scheduled_at_utc,
                error_text=None,
            )
        )

        result = await self.session.execute(statement)
        await self.session.commit()

        return result.rowcount == 1

    async def claim_for_publishing(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
        expected_status: str,
        require_due: bool = False,
    ) -> Publication | None:
        conditions = [
            Publication.id == publication_id,
            Publication.owner_telegram_id == owner_telegram_id,
            Publication.status == expected_status,
        ]

        if require_due:
            conditions.extend(
                [
                    Publication.scheduled_at.is_not(None),
                    Publication.scheduled_at <= utc_now_naive(),
                ]
            )

        statement = (
            update(Publication)
            .where(*conditions)
            .values(
                status=PublicationStatus.PUBLISHING.value,
                publishing_started_at=utc_now_naive(),
                error_text=None,
            )
        )

        result = await self.session.execute(statement)
        await self.session.commit()

        if result.rowcount != 1:
            return None

        return await self.get_by_id(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )

    async def mark_publishing(
        self,
        publication: Publication,
    ) -> bool:
        claimed = await self.claim_for_publishing(
            publication_id=publication.id,
            owner_telegram_id=publication.owner_telegram_id,
            expected_status=publication.status,
        )
        return claimed is not None

    async def mark_published(
        self,
        publication: Publication,
        *,
        telegram_message_id: int,
    ) -> bool:
        statement = (
            update(Publication)
            .where(
                Publication.id == publication.id,
                Publication.owner_telegram_id == publication.owner_telegram_id,
                Publication.status == PublicationStatus.PUBLISHING.value,
            )
            .values(
                status=PublicationStatus.PUBLISHED.value,
                telegram_message_id=telegram_message_id,
                published_at=utc_now_naive(),
                publishing_started_at=None,
                error_text=None,
            )
        )

        result = await self.session.execute(statement)
        await self.session.commit()

        return result.rowcount == 1

    async def mark_failed(
        self,
        publication: Publication,
        *,
        error_text: str,
    ) -> bool:
        statement = (
            update(Publication)
            .where(
                Publication.id == publication.id,
                Publication.owner_telegram_id == publication.owner_telegram_id,
                Publication.status.in_(
                    {
                        PublicationStatus.DRAFT.value,
                        PublicationStatus.PUBLISHING.value,
                    }
                ),
            )
            .values(
                status=PublicationStatus.FAILED.value,
                error_text=error_text[:2000],
                publishing_started_at=None,
            )
        )

        result = await self.session.execute(statement)
        await self.session.commit()

        return result.rowcount == 1

    async def cancel_if_allowed(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
        allowed_statuses: set[str],
    ) -> bool:
        statement = (
            update(Publication)
            .where(
                Publication.id == publication_id,
                Publication.owner_telegram_id == owner_telegram_id,
                Publication.status.in_(allowed_statuses),
            )
            .values(
                status=PublicationStatus.CANCELLED.value,
                publishing_started_at=None,
            )
        )

        result = await self.session.execute(statement)
        await self.session.commit()

        return result.rowcount == 1

    async def mark_cancelled(
        self,
        publication: Publication,
    ) -> bool:
        return await self.cancel_if_allowed(
            publication_id=publication.id,
            owner_telegram_id=publication.owner_telegram_id,
            allowed_statuses={
                PublicationStatus.DRAFT.value,
                PublicationStatus.SCHEDULED.value,
                PublicationStatus.FAILED.value,
            },
        )

    async def recover_stale_publishing(
        self,
        *,
        stale_before_utc: datetime,
    ) -> list[tuple[int, int]]:
        stale_condition = or_(
            Publication.publishing_started_at.is_(None),
            Publication.publishing_started_at <= stale_before_utc,
        )

        candidates_result = await self.session.execute(
            select(
                Publication.id,
                Publication.owner_telegram_id,
            ).where(
                Publication.status == PublicationStatus.PUBLISHING.value,
                stale_condition,
            )
        )
        candidates = [
            (int(publication_id), int(owner_telegram_id))
            for publication_id, owner_telegram_id in candidates_result.all()
        ]

        if not candidates:
            return []

        publication_ids = [publication_id for publication_id, _ in candidates]

        await self.session.execute(
            update(Publication)
            .where(
                Publication.id.in_(publication_ids),
                Publication.status == PublicationStatus.PUBLISHING.value,
                stale_condition,
            )
            .values(
                status=PublicationStatus.FAILED.value,
                publishing_started_at=None,
                error_text=(
                    "Публикация была прервана во время отправки. "
                    "Автоматический повтор отключён, чтобы избежать дубликата."
                ),
            )
        )
        await self.session.commit()

        return candidates
