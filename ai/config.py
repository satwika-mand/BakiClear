"""Environment-backed settings. Import `settings` anywhere; never read os.environ directly."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    # Used when gemini_model is transiently overloaded (observed live during
    # development: gemini-3.5-flash 503s while flash-lite stays up).
    gemini_fallback_model: str = "gemini-3.5-flash-lite"

    # Where customer/invoice context comes from. "mock" keeps the whole AI
    # pipeline runnable with no backend and no database.
    context_source: Literal["mock", "api"] = "mock"
    backend_base_url: str = "http://localhost:8000"

    sarvam_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
