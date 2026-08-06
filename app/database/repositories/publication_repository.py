from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Publication,
    PublicationStatus,
    PublicationVersion,
)


def utc_now_naive() -> datetime:
    """Возвращает текущее UTC-время без tzinfo для совместимости с SQLite."""
    return datetime.now(UTC).replace(tzinfo=None)


def build_publication_snapshot(publication: Publication) -> str:
    payload: dict[str, Any] = {
        "channel_id": publication.channel_id,
        "content_type": publication.content_type,
        "text": publication.text,
        "text_entities_json": publication.text_entities_json,
        "scheduled_at": (
            publication.scheduled_at.isoformat()
            if publication.scheduled_at is not None
            else None
        ),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


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
        text_entities_json: str | None = None,
    ) -> Publication:
        publication = Publication(
            owner_telegram_id=owner_telegram_id,
            channel_id=channel_id,
            content_type=content_type,
            text=text,
            text_entities_json=text_entities_json,
            telegram_file_id=telegram_file_id,
            status=PublicationStatus.DRAFT.value,
            version=1,
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

    async def list_versions(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
        limit: int = 30,
    ) -> list[PublicationVersion]:
        statement = (
            select(PublicationVersion)
            .where(
                PublicationVersion.publication_id == publication_id,
                PublicationVersion.owner_telegram_id == owner_telegram_id,
            )
            .order_by(
                PublicationVersion.version.desc(),
                PublicationVersion.id.desc(),
            )
            .limit(limit)
        )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

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
                updated_at=utc_now_naive(),
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
        text_entities_json: str | None,
        scheduled_at_utc: datetime,
        expected_version: int,
    ) -> int | None:
        previous_snapshot = build_publication_snapshot(publication)
        next_version = expected_version + 1

        statement = (
            update(Publication)
            .where(
                Publication.id == publication.id,
                Publication.owner_telegram_id == publication.owner_telegram_id,
                Publication.status == PublicationStatus.SCHEDULED.value,
                Publication.version == expected_version,
            )
            .values(
                channel_id=channel_id,
                text=text,
                text_entities_json=text_entities_json,
                scheduled_at=scheduled_at_utc,
                error_text=None,
                version=next_version,
                updated_at=utc_now_naive(),
            )
        )

        result = await self.session.execute(statement)

        if result.rowcount != 1:
            await self.session.rollback()
            return None

        self.session.add(
            PublicationVersion(
                publication_id=publication.id,
                owner_telegram_id=publication.owner_telegram_id,
                version=expected_version,
                snapshot_json=previous_snapshot,
            )
        )
        await self.session.commit()

        return next_version

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
                updated_at=utc_now_naive(),
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
                updated_at=utc_now_naive(),
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
                updated_at=utc_now_naive(),
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
                updated_at=utc_now_naive(),
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
                updated_at=utc_now_naive(),
                error_text=(
                    "Публикация была прервана во время отправки. "
                    "Автоматический повтор отключён, чтобы избежать дубликата."
                ),
            )
        )
        await self.session.commit()

        return candidates
