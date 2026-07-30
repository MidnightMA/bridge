"""Configuration management module."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loader and validator."""

    def __init__(self) -> None:
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_channel_id: str = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()

        self.bale_phone_number: str = os.getenv("BALE_PHONE_NUMBER", "").strip()
        self.bale_session: str = os.getenv("BALE_SESSION", "").strip()
        self.bale_channel_id: str = os.getenv("BALE_CHANNEL_ID", "").strip()

        self.temp_dir: Path = Path(os.getenv("MEDIA_TEMP_DIR", "temp_media"))
        self.db_path: Path = Path(os.getenv("DB_PATH", "processed_messages.db"))
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

        self.max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
        self.retry_delay: float = float(os.getenv("RETRY_DELAY", "2.0"))

    def validate(self) -> None:
        """Validates that all required environment variables are set."""
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.telegram_channel_id:
            missing.append("TELEGRAM_CHANNEL_ID")
        if not self.bale_phone_number:
            missing.append("BALE_PHONE_NUMBER")
        if not self.bale_channel_id:
            missing.append("BALE_CHANNEL_ID")

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Please check your .env file."
            )