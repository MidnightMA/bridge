"""
Configuration module for Bale-to-Telegram Channel Mirror.
Loads environment variables and validates configuration parameters.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Union
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)


@dataclass(frozen=True)
class Config:
    """Application configuration container."""

    bale_phone: str
    bale_session: str
    bale_channel_id: Union[str, int]
    telegram_bot_token: str
    telegram_channel_id: Union[str, int]

    @classmethod
    def load(cls) -> "Config":
        """
        Load and validate environment variables.
        Raises ValueError if required settings are missing.
        """
        bale_phone = os.getenv("BALE_PHONE", "").strip()
        bale_session = os.getenv("BALE_SESSION", "bale_session").strip()
        bale_channel_raw = os.getenv("BALE_CHANNEL_ID", "").strip()
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        telegram_channel_raw = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()

        missing = []
        if not bale_phone:
            missing.append("BALE_PHONE")
        if not bale_channel_raw:
            missing.append("BALE_CHANNEL_ID")
        if not telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not telegram_channel_raw:
            missing.append("TELEGRAM_CHANNEL_ID")

        if missing:
            raise ValueError(
                f"Missing required environment variable(s): {', '.join(missing)}"
            )

        # Helper to parse channel IDs (integer or string handle)
        def _parse_channel_id(raw_id: str) -> Union[str, int]:
            try:
                return int(raw_id)
            except ValueError:
                return raw_id

        return cls(
            bale_phone=bale_phone,
            bale_session=bale_session,
            bale_channel_id=_parse_channel_id(bale_channel_raw),
            telegram_bot_token=telegram_bot_token,
            telegram_channel_id=_parse_channel_id(telegram_channel_raw),
        )