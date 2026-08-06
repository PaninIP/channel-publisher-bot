from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: SecretStr
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    app_timezone: str = "Europe/Moscow"
    publication_worker_interval_seconds: int = Field(default=10, gt=0)
    publication_publishing_timeout_seconds: int = Field(default=300, gt=0)
    mini_app_url: str = ""
    mini_app_auth_max_age_seconds: int = Field(default=3600, gt=0)

    media_storage_backend: str = "local"
    media_local_root: str = "data/media"
    media_max_items: int = Field(default=10, ge=1, le=10)
    media_photo_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    media_video_max_bytes: int = Field(default=50 * 1024 * 1024, gt=0)

    media_s3_endpoint: str = ""
    media_s3_region: str = ""
    media_s3_bucket: str = ""
    media_s3_key_id: SecretStr = SecretStr("")
    media_s3_application_key: SecretStr = SecretStr("")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
