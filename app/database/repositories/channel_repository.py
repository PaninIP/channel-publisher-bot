from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Channel


class ChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_owner(
        self,
        owner_telegram_id: int,
    ) -> list[Channel]:
        statement = (
            select(Channel)
            .where(
                Channel.owner_telegram_id == owner_telegram_id,
                Channel.is_active.is_(True),
            )
            .order_by(Channel.id)
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def get_by_id(
        self,
        *,
        channel_id: int,
        owner_telegram_id: int,
    ) -> Channel | None:
        statement = select(Channel).where(
            Channel.id == channel_id,
            Channel.owner_telegram_id == owner_telegram_id,
            Channel.is_active.is_(True),
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def add_or_update(
        self,
        *,
        owner_telegram_id: int,
        telegram_chat_id: int,
        title: str,
        username: str | None,
    ) -> Channel:
        statement = select(Channel).where(
            Channel.owner_telegram_id == owner_telegram_id,
            Channel.telegram_chat_id == telegram_chat_id,
        )

        result = await self.session.execute(statement)
        channel = result.scalar_one_or_none()

        if channel is None:
            channel = Channel(
                owner_telegram_id=owner_telegram_id,
                telegram_chat_id=telegram_chat_id,
                title=title,
                username=username,
                is_active=True,
            )

            self.session.add(channel)
        else:
            channel.title = title
            channel.username = username
            channel.is_active = True

        await self.session.commit()
        await self.session.refresh(channel)

        return channel
