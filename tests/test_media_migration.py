import sqlite3
from types import SimpleNamespace

import pytest

from app.database.migrations import apply_sqlite_migrations


class FakeAsyncSqliteConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.dialect = SimpleNamespace(name="sqlite")

    async def exec_driver_sql(self, statement: str):
        cursor = self.connection.execute(statement)
        self.connection.commit()
        return cursor


@pytest.mark.asyncio
async def test_migration_adds_media_columns_and_backfills_legacy_file_id() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            CREATE TABLE publications (
                id INTEGER PRIMARY KEY,
                owner_telegram_id INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                telegram_file_id TEXT,
                created_at DATETIME
            );
            CREATE TABLE publication_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                publication_id INTEGER NOT NULL,
                owner_telegram_id INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                storage_backend TEXT NOT NULL,
                storage_key TEXT,
                telegram_file_id TEXT,
                original_filename TEXT,
                content_type TEXT,
                file_size INTEGER,
                position INTEGER NOT NULL,
                has_spoiler BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME
            );
            INSERT INTO publications (
                id, owner_telegram_id, content_type,
                telegram_file_id, created_at
            ) VALUES (
                7, 101, 'photo', 'legacy-file-id', '2026-08-06 20:00:00'
            );
            """
        )

        await apply_sqlite_migrations(FakeAsyncSqliteConnection(connection))
        await apply_sqlite_migrations(FakeAsyncSqliteConnection(connection))

        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(publications)")
        }
        assert "show_caption_above_media" in columns
        assert "telegram_message_ids_json" in columns

        media = connection.execute(
            "SELECT publication_id, storage_backend, telegram_file_id, "
            "content_type, position FROM publication_media"
        ).fetchall()
        assert media == [(7, "telegram", "legacy-file-id", "image/jpeg", 1)]
    finally:
        connection.close()
