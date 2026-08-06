from __future__ import annotations

import asyncio
import hashlib
import hmac
import shutil
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

import aiohttp

from app.config import Settings


class MediaStorageError(RuntimeError):
    pass


class MediaObjectStorage(ABC):
    backend_name: str

    @abstractmethod
    async def put_file(
        self,
        *,
        source_path: Path,
        storage_key: str,
        content_type: str,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def download_to_path(
        self,
        *,
        storage_key: str,
        destination_path: Path,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_file(self, *, storage_key: str) -> None:
        raise NotImplementedError


class LocalMediaStorage(MediaObjectStorage):
    backend_name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, storage_key: str) -> Path:
        normalized = PurePosixPath(storage_key)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise MediaStorageError("Некорректный ключ локального медиафайла.")

        destination = (self.root / Path(*normalized.parts)).resolve()
        if self.root not in destination.parents:
            raise MediaStorageError("Медиафайл выходит за пределы хранилища.")
        return destination

    async def put_file(
        self,
        *,
        source_path: Path,
        storage_key: str,
        content_type: str,
    ) -> None:
        del content_type
        destination = self._resolve_key(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")

        def copy() -> None:
            shutil.copyfile(source_path, temporary)
            temporary.replace(destination)

        await asyncio.to_thread(copy)

    async def download_to_path(
        self,
        *,
        storage_key: str,
        destination_path: Path,
    ) -> None:
        source = self._resolve_key(storage_key)
        if not source.is_file():
            raise MediaStorageError("Медиафайл отсутствует в локальном хранилище.")
        await asyncio.to_thread(shutil.copyfile, source, destination_path)

    async def delete_file(self, *, storage_key: str) -> None:
        target = self._resolve_key(storage_key)

        def delete() -> None:
            try:
                target.unlink()
            except FileNotFoundError:
                return

        await asyncio.to_thread(delete)


class S3MediaStorage(MediaObjectStorage):
    backend_name = "s3"
    service_name = "s3"

    def __init__(self, settings: Settings) -> None:
        self.endpoint = settings.media_s3_endpoint.rstrip("/")
        self.region = settings.media_s3_region.strip()
        self.bucket = settings.media_s3_bucket.strip()
        self.key_id = settings.media_s3_key_id.get_secret_value()
        self.application_key = settings.media_s3_application_key.get_secret_value()

        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path not in {"", "/"}
        ):
            raise MediaStorageError(
                "MEDIA_S3_ENDPOINT должен быть HTTPS endpoint без имени bucket."
            )
        if not all(
            [
                self.region,
                self.bucket,
                self.key_id,
                self.application_key,
            ]
        ):
            raise MediaStorageError(
                "Для S3-хранилища заполните endpoint, region, bucket, key ID и key."
            )
        self.host = parsed.netloc

    @staticmethod
    def _payload_hash(path: Path | None) -> str:
        digest = hashlib.sha256()
        if path is not None:
            with path.open("rb") as file:
                for chunk in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sign(key: bytes, value: str) -> bytes:
        return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()

    def _request_parts(self, storage_key: str) -> tuple[str, str]:
        normalized = PurePosixPath(storage_key)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise MediaStorageError("Некорректный S3 object key.")

        encoded_bucket = quote(self.bucket, safe="")
        encoded_key = "/".join(quote(part, safe="~") for part in normalized.parts)
        canonical_uri = f"/{encoded_bucket}/{encoded_key}"
        return f"{self.endpoint}{canonical_uri}", canonical_uri

    def _signed_headers(
        self,
        *,
        method: str,
        canonical_uri: str,
        payload_hash: str,
        content_type: str | None,
        now: datetime,
    ) -> dict[str, str]:
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        headers_to_sign = {
            "host": self.host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if content_type:
            headers_to_sign["content-type"] = content_type

        ordered_names = sorted(headers_to_sign)
        canonical_headers = "".join(
            f"{name}:{headers_to_sign[name].strip()}\n" for name in ordered_names
        )
        signed_headers = ";".join(ordered_names)
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )

        credential_scope = (
            f"{date_stamp}/{self.region}/{self.service_name}/aws4_request"
        )
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )

        date_key = self._sign(
            ("AWS4" + self.application_key).encode("utf-8"),
            date_stamp,
        )
        region_key = self._sign(date_key, self.region)
        service_key = self._sign(region_key, self.service_name)
        signing_key = self._sign(service_key, "aws4_request")
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Host": self.host,
            "X-Amz-Content-Sha256": payload_hash,
            "X-Amz-Date": amz_date,
            "Authorization": (
                "AWS4-HMAC-SHA256 "
                f"Credential={self.key_id}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, "
                f"Signature={signature}"
            ),
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    async def _raise_for_status(self, response: aiohttp.ClientResponse) -> None:
        if 200 <= response.status < 300:
            return
        body = (await response.text())[:1000]
        raise MediaStorageError(
            f"S3 вернул HTTP {response.status}: {body or response.reason}"
        )

    async def put_file(
        self,
        *,
        source_path: Path,
        storage_key: str,
        content_type: str,
    ) -> None:
        payload_hash = await asyncio.to_thread(self._payload_hash, source_path)
        url, canonical_uri = self._request_parts(storage_key)
        headers = self._signed_headers(
            method="PUT",
            canonical_uri=canonical_uri,
            payload_hash=payload_hash,
            content_type=content_type,
            now=datetime.now(UTC),
        )
        headers["Content-Length"] = str(source_path.stat().st_size)

        timeout = aiohttp.ClientTimeout(total=600)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            with source_path.open("rb") as file:
                async with session.put(url, data=file, headers=headers) as response:
                    await self._raise_for_status(response)

    async def download_to_path(
        self,
        *,
        storage_key: str,
        destination_path: Path,
    ) -> None:
        payload_hash = self._payload_hash(None)
        url, canonical_uri = self._request_parts(storage_key)
        headers = self._signed_headers(
            method="GET",
            canonical_uri=canonical_uri,
            payload_hash=payload_hash,
            content_type=None,
            now=datetime.now(UTC),
        )

        timeout = aiohttp.ClientTimeout(total=600)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                await self._raise_for_status(response)
                with destination_path.open("wb") as file:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        file.write(chunk)

    async def delete_file(self, *, storage_key: str) -> None:
        payload_hash = self._payload_hash(None)
        url, canonical_uri = self._request_parts(storage_key)
        headers = self._signed_headers(
            method="DELETE",
            canonical_uri=canonical_uri,
            payload_hash=payload_hash,
            content_type=None,
            now=datetime.now(UTC),
        )

        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.delete(url, headers=headers) as response:
                await self._raise_for_status(response)


def get_media_storage_for_backend(
    settings: Settings,
    backend_name: str,
) -> MediaObjectStorage:
    backend = backend_name.strip().lower()
    if backend == "local":
        return LocalMediaStorage(settings.media_local_root)
    if backend == "s3":
        return S3MediaStorage(settings)
    raise MediaStorageError("MEDIA_STORAGE_BACKEND должен иметь значение local или s3.")


def get_media_storage(settings: Settings) -> MediaObjectStorage:
    return get_media_storage_for_backend(
        settings,
        settings.media_storage_backend,
    )
