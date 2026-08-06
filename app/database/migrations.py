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
        "show_caption_above_media": (
            "ALTER TABLE publications "
            "ADD COLUMN show_caption_above_media BOOLEAN NOT NULL DEFAULT 0"
        ),
        "telegram_message_ids_json": (
            "ALTER TABLE publications ADD COLUMN telegram_message_ids_json TEXT NULL"
        ),
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

    await connection.exec_driver_sql(
        "INSERT INTO publication_media ("
        "publication_id, owner_telegram_id, media_type, storage_backend, "
        "telegram_file_id, content_type, position, has_spoiler, "
        "created_at, updated_at"
        ") "
        "SELECT p.id, p.owner_telegram_id, p.content_type, 'telegram', "
        "p.telegram_file_id, "
        "CASE p.content_type "
        "WHEN 'photo' THEN 'image/jpeg' "
        "WHEN 'video' THEN 'video/mp4' END, "
        "1, 0, COALESCE(p.created_at, CURRENT_TIMESTAMP), "
        "COALESCE(p.updated_at, p.created_at, CURRENT_TIMESTAMP) "
        "FROM publications p "
        "WHERE p.telegram_file_id IS NOT NULL "
        "AND p.content_type IN ('photo', 'video') "
        "AND NOT EXISTS ("
        "SELECT 1 FROM publication_media m WHERE m.publication_id = p.id"
        ")"
    )
