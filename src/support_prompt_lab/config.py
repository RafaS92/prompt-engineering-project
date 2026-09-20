from functools import lru_cache

from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://support_prompt_lab:support_prompt_lab@localhost:5432/"
        "support_prompt_lab"
    )
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()
