"""
Telegram Client module for communicating with Telegram Bot API.
"""

import logging
from pathlib import Path
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class TelegramClient:
    """Async wrapper for Telegram Bot API message dispatching."""

    def __init__(self, bot_token: str, channel_id: str) -> None:
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Initializes the HTTPX client session."""
        if not self.client or self.client.is_closed:
            self.client = httpx.AsyncClient(timeout=120.0)
            logger.info("Telegram HTTP client initialized.")

    async def stop(self) -> None:
        """Closes the HTTPX client session."""
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            logger.info("Telegram HTTP client closed.")

    async def send_text(self, text: str) -> bool:
        """Send plain text message to the target Telegram channel."""
        if not self.client:
            raise RuntimeError("Telegram client is not running.")
        
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": self.channel_id,
            "text": text,
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            res_data = response.json()
            if res_data.get("ok"):
                logger.info(f"Successfully forwarded text message to Telegram channel ({self.channel_id})")
                return True
            logger.error(f"Telegram API returned error: {res_data.get('description')}")
            return False
        except Exception as e:
            logger.error(f"Failed to send text message to Telegram: {e}", exc_info=True)
            return False

    async def send_photo(self, photo_path: Path, caption: Optional[str] = None) -> bool:
        """Send photo with optional caption to Telegram channel."""
        if not self.client:
            raise RuntimeError("Telegram client is not running.")
        
        url = f"{self.api_url}/sendPhoto"
        data = {"chat_id": self.channel_id}
        if caption:
            data["caption"] = caption

        try:
            with open(photo_path, "rb") as file_bytes:
                files = {"photo": (photo_path.name, file_bytes, "image/jpeg")}
                response = await self.client.post(url, data=data, files=files)
            
            response.raise_for_status()
            res_data = response.json()
            if res_data.get("ok"):
                logger.info(f"Successfully forwarded photo to Telegram channel ({self.channel_id})")
                return True
            logger.error(f"Telegram API photo error: {res_data.get('description')}")
            return False
        except Exception as e:
            logger.error(f"Failed to upload photo to Telegram: {e}", exc_info=True)
            return False

    async def send_video(self, video_path: Path, caption: Optional[str] = None) -> bool:
        """Send video with optional caption to Telegram channel."""
        if not self.client:
            raise RuntimeError("Telegram client is not running.")
        
        url = f"{self.api_url}/sendVideo"
        data = {"chat_id": self.channel_id}
        if caption:
            data["caption"] = caption

        try:
            with open(video_path, "rb") as file_bytes:
                files = {"video": (video_path.name, file_bytes, "video/mp4")}
                response = await self.client.post(url, data=data, files=files)

            response.raise_for_status()
            res_data = response.json()
            if res_data.get("ok"):
                logger.info(f"Successfully forwarded video to Telegram channel ({self.channel_id})")
                return True
            logger.error(f"Telegram API video error: {res_data.get('description')}")
            return False
        except Exception as e:
            logger.error(f"Failed to upload video to Telegram: {e}", exc_info=True)
            return False