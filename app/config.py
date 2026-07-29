from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: SecretStr
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    app_timezone: str = "Europe/Moscow"
    publication_worker_interval_seconds: int = 10
    mini_app_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
