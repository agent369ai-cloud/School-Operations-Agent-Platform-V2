"""Centralised settings. Every value is overridable via env var or .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # LLM
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"

    # Database
    DATABASE_URL: str = "sqlite:///./school.db"

    # Auth
    SECRET_KEY: str = "insecure-default-change-me"
    JWT_EXPIRE_HOURS: int = 8

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""

    # Scheduler policy
    QUIET_HOURS_START: int = 20
    QUIET_HOURS_END: int = 8

    # App
    APP_ENV: str = "development"


settings = Settings()
