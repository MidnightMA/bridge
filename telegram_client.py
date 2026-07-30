"""Async client for Telegram Bot API using aiohttp."""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import aiohttp

logger = logging.getLogger("bridge.telegram")


class TelegramClient:
    """Handles communication with the Telegram Bot API with automatic retries."""

    def __init__(
        self,
        bot_token: str,
        target_channel_id: str,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> None:
        self.bot_token = bot_token
        self.target_channel_id = target_channel_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """Executes an HTTP request to the Telegram Bot API with exponential backoff."""
        url = f"{self.base_url}/{endpoint}"
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url, **kwargs) as response:
                        res_json = await response.json()

                        if response.status == 200 and res_json.get("ok"):
                            return res_json

                        # Handle Telegram rate limits (HTTP 429)
                        if response.status == 429:
                            retry_after = res_json.get("parameters", {}).get(
                                "retry_after", self.retry_delay
                            )
                            logger.warning(
                                f"Telegram rate limit hit. Sleeping for {retry_after}s..."
                            )
                            await asyncio.sleep(retry_after)
                            continue

                        err_msg = res_json.get("description", f"HTTP {response.status}")
                        logger.error(
                            f"Telegram API Error [Attempt {attempt}/{self.max_retries}]: {err_msg}"
                        )
                        last_exception = RuntimeError(f"Telegram API Error: {err_msg}")

            except Exception as e:
                logger.error(
                    f"Network error sending request to Telegram [Attempt {attempt}/{self.max_retries}]: {e}"
                )
                last_exception = e

            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay * (2 ** (attempt - 1)))

        raise last_exception or RuntimeError(
            f"Failed to execute Telegram API call: {endpoint}"
        )

    async def send_text(self, text: str) -> Dict[str, Any]:
        """Sends a text message to the target Telegram channel."""
        payload = {
            "chat_id": self.target_channel_id,
            "text": text,
            "disable_web_page_preview": False,
        }
        return await self._request("POST", "sendMessage", json=payload)

    async def send_photo(
        self, photo_path: Path, caption: Optional[str] = None
    ) -> Dict[str, Any]:
        """Uploads and sends a photo to the target Telegram channel."""
        data = aiohttp.FormData()
        data.add_field("chat_id", self.target_channel_id)
        if caption:
            data.add_field("caption", caption)

        with open(photo_path, "rb") as f:
            data.add_field("photo", f, filename=photo_path.name)
            return await self._request("POST", "sendPhoto", data=data)

    async def send_video(
        self, video_path: Path, caption: Optional[str] = None
    ) -> Dict[str, Any]:
        """Uploads and sends a video to the target Telegram channel."""
        data = aiohttp.FormData()
        data.add_field("chat_id", self.target_channel_id)
        if caption:
            data.add_field("caption", caption)

        with open(video_path, "rb") as f:
            data.add_field("video", f, filename=video_path.name)
            return await self._request("POST", "sendVideo", data=data)