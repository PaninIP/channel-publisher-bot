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

    migrations = {
        "publishing_started_at": (
            "ALTER TABLE publications ADD COLUMN publishing_started_at DATETIME NULL"
        ),
        "text_entities_json": (
            "ALTER TABLE publications ADD COLUMN text_entities_json TEXT NULL"
        ),
        "version": (
            "ALTER TABLE publications ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
        ),
        "updated_at": ("ALTER TABLE publications ADD COLUMN updated_at DATETIME NULL"),
    }

    for column_name, statement in migrations.items():
        if column_name in columns:
            continue

        logger.info(
            "Applying SQLite migration: add publications.%s",
            column_name,
        )
        await connection.exec_driver_sql(statement)

    await connection.exec_driver_sql(
        "UPDATE publications SET version = 1 WHERE version IS NULL OR version < 1"
    )
    await connection.exec_driver_sql(
        "UPDATE publications "
        "SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
    )
