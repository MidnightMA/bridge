"""
Configuration module for Bale-to-Telegram Channel Mirror.
Loads environment variables and validates configuration parameters.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional, Union
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
    telegram_proxy_url: Optional[str] = None
    telegram_connect_timeout: float = 30.0
    telegram_read_timeout: float = 60.0

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
        telegram_proxy_url = os.getenv("TELEGRAM_PROXY_URL", "").strip() or None

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

        def _parse_channel_id(raw_id: str) -> Union[str, int]:
            try:
                return int(raw_id)
            except ValueError:
                return raw_id

        try:
            connect_timeout = float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "30.0"))
        except ValueError:
            connect_timeout = 30.0

        try:
            read_timeout = float(os.getenv("TELEGRAM_READ_TIMEOUT", "60.0"))
        except ValueError:
            read_timeout = 60.0

        return cls(
            bale_phone=bale_phone,
            bale_session=bale_session,
            bale_channel_id=_parse_channel_id(bale_channel_raw),
            telegram_bot_token=telegram_bot_token,
            telegram_channel_id=_parse_channel_id(telegram_channel_raw),
            telegram_proxy_url=telegram_proxy_url,
            telegram_connect_timeout=connect_timeout,
            telegram_read_timeout=read_timeout,
        )