from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PublicationContentType(StrEnum):
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"


class PublicationStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SCHEDULED = "scheduled"


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    owner_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )

    channel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "channels.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    content_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    telegram_file_id: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PublicationStatus.DRAFT.value,
        index=True,
    )

    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    error_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
