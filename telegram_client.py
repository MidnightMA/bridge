"""
Telegram client wrapper using python-telegram-bot.
Handles uploading text, photo, video, and media group albums to Telegram channel with proxy and timeout support.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from telegram import Bot, InputMediaPhoto, InputMediaVideo
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

logger = logging.getLogger(__name__)

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_TEXT_LIMIT = 4096


class TelegramClient:
    """Async Telegram Bot client for posting messages to a target channel."""

    def __init__(
        self,
        token: str,
        channel_id: Union[int, str],
        proxy_url: Optional[str] = None,
        connect_timeout: float = 30.0,
        read_timeout: float = 60.0,
    ) -> None:
        """
        Initialize Telegram client.

        :param token: Bot API token from @BotFather
        :param channel_id: Target channel ID or username
        :param proxy_url: Optional HTTP/SOCKS5 proxy URL
        :param connect_timeout: HTTP connect timeout in seconds
        :param read_timeout: HTTP read timeout in seconds
        """
        self.channel_id = channel_id

        request_kwargs = {
            "connect_timeout": connect_timeout,
            "read_timeout": read_timeout,
            "write_timeout": read_timeout,
            "connection_pool_size": 8,
        }

        if proxy_url:
            request_kwargs["proxy_url"] = proxy_url
            logger.info("Using Telegram Proxy: %s", proxy_url)

        request = HTTPXRequest(**request_kwargs)
        self.bot = Bot(token=token, request=request)

    async def initialize(self) -> None:
        """Test API connectivity and bot validity."""
        try:
            bot_info = await self.bot.get_me()
            logger.info("Connected to Telegram as @%s (Bot ID: %s)", bot_info.username, bot_info.id)
        except Exception as e:
            logger.error("Failed to connect to Telegram Bot API: %s", e)
            raise

    async def send_text_message(self, text: str) -> Optional[int]:
        """Send plain text to Telegram channel."""
        if not text:
            return None

        if len(text) > TELEGRAM_TEXT_LIMIT:
            logger.warning("Text exceeds Telegram limit (%d chars). Truncating.", TELEGRAM_TEXT_LIMIT)
            text = text[: TELEGRAM_TEXT_LIMIT - 3] + "..."

        try:
            msg = await self.bot.send_message(
                chat_id=self.channel_id,
                text=text,
            )
            return msg.message_id
        except TelegramError as e:
            logger.error("Telegram error sending text: %s", e)
            return None

    async def send_photo_message(
        self, photo_bytes: bytes, caption: Optional[str] = None
    ) -> Optional[int]:
        """Upload photo file bytes to Telegram channel with caption."""
        if not photo_bytes:
            return None

        formatted_caption = self._format_caption(caption)

        try:
            msg = await self.bot.send_photo(
                chat_id=self.channel_id,
                photo=photo_bytes,
                caption=formatted_caption,
            )
            return msg.message_id
        except TelegramError as e:
            logger.error("Telegram error uploading photo: %s", e)
            return None

    async def send_video_message(
        self, video_bytes: bytes, caption: Optional[str] = None
    ) -> Optional[int]:
        """Upload video file bytes to Telegram channel with caption."""
        if not video_bytes:
            return None

        formatted_caption = self._format_caption(caption)

        try:
            msg = await self.bot.send_video(
                chat_id=self.channel_id,
                video=video_bytes,
                caption=formatted_caption,
            )
            return msg.message_id
        except TelegramError as e:
            logger.error("Telegram error uploading video: %s", e)
            return None

    async def send_media_group(self, items: List[Dict[str, Any]]) -> Optional[List[int]]:
        """
        Send a media group (album) to the Telegram channel.
        items elements contain: {'type': MessageType, 'bytes': bytes, 'caption': Optional[str]}
        """
        if not items:
            return None

        # Extract caption from whichever item has a non-empty caption string
        album_caption = None
        for item in items:
            if item.get("caption"):
                album_caption = item["caption"]
                break

        formatted_caption = self._format_caption(album_caption)

        media_list = []
        for idx, item in enumerate(items):
            cap = formatted_caption if idx == 0 else None
            # Compare by string representation or type name
            type_str = str(item.get("type", "")).lower()

            if "photo" in type_str:
                media_list.append(InputMediaPhoto(media=item["bytes"], caption=cap))
            elif "video" in type_str:
                media_list.append(InputMediaVideo(media=item["bytes"], caption=cap))

        if not media_list:
            return None

        try:
            messages = await self.bot.send_media_group(
                chat_id=self.channel_id,
                media=media_list,
            )
            return [m.message_id for m in messages]
        except TelegramError as e:
            logger.error("Failed to send media group to Telegram: %s", e)
            return None

    @staticmethod
    def _format_caption(caption: Optional[str]) -> Optional[str]:
        """Format and truncate caption to fit Telegram bounds."""
        if not caption:
            return None
        caption = caption.strip()
        if len(caption) > TELEGRAM_CAPTION_LIMIT:
            logger.warning("Caption exceeds Telegram limit (%d chars). Truncating.", TELEGRAM_CAPTION_LIMIT)
            return caption[: TELEGRAM_CAPTION_LIMIT - 3] + "..."
        return caption