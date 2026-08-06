from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from uuid import uuid4

from app.config import get_settings
from app.services.media_storage import get_media_storage


async def main() -> None:
    settings = get_settings()
    storage = get_media_storage(settings)
    storage_key = f"healthchecks/{uuid4().hex}.txt"
    expected = b"channel-publisher-media-storage-check\n"

    with tempfile.TemporaryDirectory(prefix="media-storage-check-") as directory:
        source = Path(directory) / "source.txt"
        destination = Path(directory) / "destination.txt"
        source.write_bytes(expected)

        try:
            await storage.put_file(
                source_path=source,
                storage_key=storage_key,
                content_type="text/plain",
            )
            await storage.download_to_path(
                storage_key=storage_key,
                destination_path=destination,
            )
            if destination.read_bytes() != expected:
                raise RuntimeError(
                    "Хранилище вернуло содержимое, отличное от загруженного."
                )
        finally:
            await storage.delete_file(storage_key=storage_key)

    print(f"Media storage check passed: {storage.backend_name}")


if __name__ == "__main__":
    asyncio.run(main())
