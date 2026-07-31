"""
Telegram client wrapper using python-telegram-bot.
Handles uploading text, photo, video, and album media groups to Telegram channel.
"""

import logging
from typing import Any, Optional, Union
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
        """Initialize Telegram client."""
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

    async def send_media_group_message(self, items: list[Any]) -> bool:
        """
        Send a list of photo/video items as a Telegram Media Group (Album).

        :param items: List of NormalizedMessage objects
        :return: True if sent successfully, False otherwise
        """
        if not items:
            return False

        if len(items) == 1:
            item = items[0]
            if item.msg_type.name == "PHOTO":
                return bool(await self.send_photo_message(item.media_bytes, item.caption))
            elif item.msg_type.name == "VIDEO":
                return bool(await self.send_video_message(item.media_bytes, item.caption))
            return False

        success_all = True

        # Telegram limits media group size to 10 items
        for i in range(0, len(items), 10):
            chunk = items[i:i + 10]
            if len(chunk) == 1:
                item = chunk[0]
                if item.msg_type.name == "PHOTO":
                    res = await self.send_photo_message(item.media_bytes, item.caption)
                elif item.msg_type.name == "VIDEO":
                    res = await self.send_video_message(item.media_bytes, item.caption)
                else:
                    res = None
                if not res:
                    success_all = False
            else:
                res = await self._send_single_media_group(chunk)
                if not res:
                    success_all = False

        return success_all

    async def _send_single_media_group(self, chunk: list[Any]) -> bool:
        """Helper to upload a chunk of max 10 items as a single media group."""
        media_list = []
        for item in chunk:
            formatted_caption = self._format_caption(item.caption)

            if item.msg_type.name == "PHOTO" and item.media_bytes:
                media_list.append(
                    InputMediaPhoto(media=item.media_bytes, caption=formatted_caption)
                )
            elif item.msg_type.name == "VIDEO" and item.media_bytes:
                media_list.append(
                    InputMediaVideo(media=item.media_bytes, caption=formatted_caption)
                )

        if not media_list:
            return False

        try:
            await self.bot.send_media_group(
                chat_id=self.channel_id,
                media=media_list,
            )
            logger.info("Forwarded album (%d media items) to Telegram successfully", len(media_list))
            return True
        except TelegramError as e:
            logger.error("Failed to send media group to Telegram: %s", e)
            return False

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