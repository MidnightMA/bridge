"""
Configuration settings module for the Bale to Telegram Mirror application.
Loads and validates environment variables.
"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings schema and environment loader."""
    
    # Bale Settings
    bale_phone: str = Field(..., validation_alias="BALE_PHONE")
    source_bale_channel: str = Field(..., validation_alias="SOURCE_BALE_CHANNEL")

    # Telegram Settings
    telegram_bot_token: str = Field(..., validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_channel_id: str = Field(..., validation_alias="TELEGRAM_CHANNEL_ID")

    # Operational Settings
    session_dir: str = Field(default="./session_data", validation_alias="SESSION_DIR")
    media_dir: str = Field(default="./temp_media", validation_alias="MEDIA_DIR")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    reconnect_delay: int = Field(default=5, validation_alias="RECONNECT_DELAY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()