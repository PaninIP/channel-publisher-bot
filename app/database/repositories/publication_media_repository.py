from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Publication,
    PublicationContentType,
    PublicationMedia,
    PublicationStatus,
    PublicationVersion,
)
from app.database.repositories.publication_repository import (
    build_publication_snapshot,
    utc_now_naive,
)
from app.services.content_plan_editor import normalize_publication_text


class PublicationMediaConflictError(RuntimeError):
    pass


class PublicationMediaValidationError(ValueError):
    pass


@dataclass(slots=True)
class MediaMutationResult:
    version: int
    content_type: str
    media: list[PublicationMedia]
    show_caption_above_media: bool


@dataclass(slots=True)
class RemovedMediaResult(MediaMutationResult):
    removed: PublicationMedia


def publication_content_type(media_types: list[str]) -> str:
    if not media_types:
        return PublicationContentType.TEXT.value
    if len(media_types) == 1:
        return media_types[0]
    return PublicationContentType.ALBUM.value


class PublicationMediaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_publication(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
    ) -> list[PublicationMedia]:
        result = await self.session.execute(
            select(PublicationMedia)
            .where(
                PublicationMedia.publication_id == publication_id,
                PublicationMedia.owner_telegram_id == owner_telegram_id,
            )
            .order_by(PublicationMedia.position, PublicationMedia.id)
        )
        return list(result.scalars().all())

    async def get_by_id(
        self,
        *,
        publication_id: int,
        media_id: int,
        owner_telegram_id: int,
    ) -> PublicationMedia | None:
        result = await self.session.execute(
            select(PublicationMedia).where(
                PublicationMedia.id == media_id,
                PublicationMedia.publication_id == publication_id,
                PublicationMedia.owner_telegram_id == owner_telegram_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_editable_publication(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
    ) -> Publication:
        result = await self.session.execute(
            select(Publication).where(
                Publication.id == publication_id,
                Publication.owner_telegram_id == owner_telegram_id,
            )
        )
        publication = result.scalar_one_or_none()
        if publication is None:
            raise PublicationMediaValidationError("Публикация не найдена.")
        if publication.status != PublicationStatus.SCHEDULED.value:
            raise PublicationMediaConflictError(
                "Медиа можно менять только у запланированной публикации."
            )
        return publication

    async def _commit_versioned_change(
        self,
        *,
        publication: Publication,
        current_media: list[PublicationMedia],
        expected_version: int,
        content_type: str,
        show_caption_above_media: bool | None = None,
    ) -> tuple[int, bool]:
        next_version = expected_version + 1
        next_show_caption_above = (
            False
            if content_type == PublicationContentType.TEXT.value
            else (
                show_caption_above_media
                if show_caption_above_media is not None
                else publication.show_caption_above_media
            )
        )
        values: dict[str, object] = {
            "content_type": content_type,
            "version": next_version,
            "updated_at": utc_now_naive(),
            "error_text": None,
            "show_caption_above_media": next_show_caption_above,
        }

        result = await self.session.execute(
            update(Publication)
            .where(
                Publication.id == publication.id,
                Publication.owner_telegram_id == publication.owner_telegram_id,
                Publication.status == PublicationStatus.SCHEDULED.value,
                Publication.version == expected_version,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            await self.session.rollback()
            raise PublicationMediaConflictError(
                "Публикация уже изменилась. Обновите редактор."
            )

        self.session.add(
            PublicationVersion(
                publication_id=publication.id,
                owner_telegram_id=publication.owner_telegram_id,
                version=expected_version,
                snapshot_json=build_publication_snapshot(
                    publication,
                    current_media,
                ),
            )
        )
        return next_version, next_show_caption_above

    async def add_uploaded(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
        expected_version: int,
        media_type: str,
        storage_backend: str,
        storage_key: str,
        original_filename: str,
        content_type: str,
        file_size: int,
        max_items: int,
    ) -> MediaMutationResult:
        publication = await self._get_editable_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        current_media = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        if len(current_media) >= max_items:
            raise PublicationMediaValidationError(
                f"В одной публикации допускается не более {max_items} вложений."
            )

        media_types = [item.media_type for item in current_media] + [media_type]
        next_content_type = publication_content_type(media_types)
        normalize_publication_text(
            publication.text,
            content_type=next_content_type,
        )
        next_version, next_show_caption_above = await self._commit_versioned_change(
            publication=publication,
            current_media=current_media,
            expected_version=expected_version,
            content_type=next_content_type,
        )

        media = PublicationMedia(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
            media_type=media_type,
            storage_backend=storage_backend,
            storage_key=storage_key,
            original_filename=original_filename[:255],
            content_type=content_type,
            file_size=file_size,
            position=len(current_media) + 1,
        )
        self.session.add(media)
        await self.session.commit()
        await self.session.refresh(media)
        items = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        return MediaMutationResult(
            next_version,
            next_content_type,
            items,
            next_show_caption_above,
        )

    async def replace_uploaded(
        self,
        *,
        publication_id: int,
        media_id: int,
        owner_telegram_id: int,
        expected_version: int,
        media_type: str,
        storage_backend: str,
        storage_key: str,
        original_filename: str,
        content_type: str,
        file_size: int,
    ) -> tuple[MediaMutationResult, PublicationMedia]:
        publication = await self._get_editable_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        current_media = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        target = next((item for item in current_media if item.id == media_id), None)
        if target is None:
            raise PublicationMediaValidationError("Вложение не найдено.")

        media_types = [
            media_type if item.id == media_id else item.media_type
            for item in current_media
        ]
        next_content_type = publication_content_type(media_types)
        normalize_publication_text(
            publication.text,
            content_type=next_content_type,
        )
        next_version, next_show_caption_above = await self._commit_versioned_change(
            publication=publication,
            current_media=current_media,
            expected_version=expected_version,
            content_type=next_content_type,
        )

        previous = PublicationMedia(
            id=target.id,
            publication_id=target.publication_id,
            owner_telegram_id=target.owner_telegram_id,
            media_type=target.media_type,
            storage_backend=target.storage_backend,
            storage_key=target.storage_key,
            telegram_file_id=target.telegram_file_id,
            original_filename=target.original_filename,
            content_type=target.content_type,
            file_size=target.file_size,
            position=target.position,
            has_spoiler=target.has_spoiler,
        )
        target.media_type = media_type
        target.storage_backend = storage_backend
        target.storage_key = storage_key
        target.telegram_file_id = None
        target.original_filename = original_filename[:255]
        target.content_type = content_type
        target.file_size = file_size
        target.updated_at = utc_now_naive()
        await self.session.commit()

        items = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        return (
            MediaMutationResult(
                next_version,
                next_content_type,
                items,
                next_show_caption_above,
            ),
            previous,
        )

    async def remove(
        self,
        *,
        publication_id: int,
        media_id: int,
        owner_telegram_id: int,
        expected_version: int,
    ) -> RemovedMediaResult:
        publication = await self._get_editable_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        current_media = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        target = next((item for item in current_media if item.id == media_id), None)
        if target is None:
            raise PublicationMediaValidationError("Вложение не найдено.")

        removed = PublicationMedia(
            id=target.id,
            publication_id=target.publication_id,
            owner_telegram_id=target.owner_telegram_id,
            media_type=target.media_type,
            storage_backend=target.storage_backend,
            storage_key=target.storage_key,
            telegram_file_id=target.telegram_file_id,
            original_filename=target.original_filename,
            content_type=target.content_type,
            file_size=target.file_size,
            position=target.position,
            has_spoiler=target.has_spoiler,
        )
        remaining = [item for item in current_media if item.id != media_id]
        next_content_type = publication_content_type(
            [item.media_type for item in remaining]
        )
        normalize_publication_text(
            publication.text,
            content_type=next_content_type,
        )
        next_version, next_show_caption_above = await self._commit_versioned_change(
            publication=publication,
            current_media=current_media,
            expected_version=expected_version,
            content_type=next_content_type,
        )

        await self.session.delete(target)
        for position, item in enumerate(remaining, start=1):
            item.position = position
            item.updated_at = utc_now_naive()
        await self.session.commit()

        items = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        return RemovedMediaResult(
            version=next_version,
            content_type=next_content_type,
            media=items,
            show_caption_above_media=next_show_caption_above,
            removed=removed,
        )

    async def reorder(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
        expected_version: int,
        media_ids: list[int],
    ) -> MediaMutationResult:
        publication = await self._get_editable_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        current_media = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        current_ids = [item.id for item in current_media]
        if len(media_ids) != len(set(media_ids)) or set(media_ids) != set(current_ids):
            raise PublicationMediaValidationError(
                "Порядок должен содержать каждое текущее вложение ровно один раз."
            )

        next_version, next_show_caption_above = await self._commit_versioned_change(
            publication=publication,
            current_media=current_media,
            expected_version=expected_version,
            content_type=publication.content_type,
        )
        by_id = {item.id: item for item in current_media}
        for position, media_id in enumerate(media_ids, start=1):
            item = by_id[media_id]
            item.position = position
            item.updated_at = utc_now_naive()
        await self.session.commit()

        items = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        return MediaMutationResult(
            next_version,
            publication.content_type,
            items,
            next_show_caption_above,
        )

    async def set_options(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
        expected_version: int,
        media_id: int | None,
        has_spoiler: bool | None,
        show_caption_above_media: bool | None,
    ) -> MediaMutationResult:
        publication = await self._get_editable_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        current_media = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        target = None
        if media_id is not None:
            target = next((item for item in current_media if item.id == media_id), None)
            if target is None:
                raise PublicationMediaValidationError("Вложение не найдено.")

        next_version, next_show_caption_above = await self._commit_versioned_change(
            publication=publication,
            current_media=current_media,
            expected_version=expected_version,
            content_type=publication.content_type,
            show_caption_above_media=show_caption_above_media,
        )
        if target is not None and has_spoiler is not None:
            target.has_spoiler = has_spoiler
            target.updated_at = utc_now_naive()
        await self.session.commit()
        items = await self.list_by_publication(
            publication_id=publication_id,
            owner_telegram_id=owner_telegram_id,
        )
        return MediaMutationResult(
            next_version,
            publication.content_type,
            items,
            next_show_caption_above,
        )

    async def cache_telegram_file_ids(
        self,
        *,
        publication_id: int,
        owner_telegram_id: int,
        file_ids_by_media_id: dict[int, str],
    ) -> None:
        for media_id, file_id in file_ids_by_media_id.items():
            await self.session.execute(
                update(PublicationMedia)
                .where(
                    PublicationMedia.id == media_id,
                    PublicationMedia.publication_id == publication_id,
                    PublicationMedia.owner_telegram_id == owner_telegram_id,
                )
                .values(
                    telegram_file_id=file_id,
                    updated_at=utc_now_naive(),
                )
            )
        await self.session.commit()
