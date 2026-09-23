from functools import lru_cache

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from support_prompt_lab.prompts import PromptStrategy


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
    triage_prompt_strategy: PromptStrategy = PromptStrategy.ZERO_SHOT
    policy_decision_sample_count: int = Field(default=1, ge=1, le=5)

    @field_validator("policy_decision_sample_count")
    @classmethod
    def sample_count_is_odd(cls, value: int) -> int:
        if value % 2 == 0:
            raise ValueError("policy_decision_sample_count must be odd")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()
