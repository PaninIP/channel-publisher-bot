from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.database.base import Base
from app.database.migrations import apply_sqlite_migrations
from app.database.models import (  # noqa: F401
    Channel,
    Publication,
    PublicationVersion,
)

settings = get_settings()

if settings.database_url.startswith("sqlite"):
    Path("data").mkdir(
        parents=True,
        exist_ok=True,
    )


engine = create_async_engine(
    settings.database_url,
    echo=False,
)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
        )
        await apply_sqlite_migrations(connection)


async def close_database() -> None:
    await engine.dispose()
