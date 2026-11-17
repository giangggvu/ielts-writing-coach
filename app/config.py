from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://coach:coach@localhost:5432/coach"

    # Auth
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_expire_minutes: int = 60 * 24

    # AI provider: "gemini", "openai_compatible" or "fake" (offline demo, no key needed)
    llm_provider: Literal["gemini", "openai_compatible", "fake"] = "fake"
    llm_model: str = "gemini-flash-latest"
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None  # only for openai_compatible
    llm_timeout_seconds: float = 90.0

    # Limits
    user_daily_limit: int = 5
    global_daily_limit: int = 200
    quota_timezone: str = "Asia/Ho_Chi_Minh"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
