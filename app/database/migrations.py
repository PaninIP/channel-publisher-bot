import logging

from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


async def apply_sqlite_migrations(
    connection: AsyncConnection,
) -> None:
    """Применяет небольшие идемпотентные миграции для текущего SQLite MVP."""
    if connection.dialect.name != "sqlite":
        return

    result = await connection.exec_driver_sql("PRAGMA table_info(publications)")
    columns = {str(row[1]) for row in result.fetchall()}

    if "publishing_started_at" not in columns:
        logger.info("Applying SQLite migration: add publications.publishing_started_at")
        await connection.exec_driver_sql(
            "ALTER TABLE publications ADD COLUMN publishing_started_at DATETIME NULL"
        )
