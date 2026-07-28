from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Channel(Base):
    __tablename__ = "channels"

    __table_args__ = (
        UniqueConstraint(
            "owner_telegram_id",
            "telegram_chat_id",
            name="uq_channels_owner_chat",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    owner_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )

    telegram_chat_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )