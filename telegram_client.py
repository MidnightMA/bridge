"""
Telegram client wrapper using python-telegram-bot.
Handles uploading text, photo, and video messages to Telegram channel.
"""

import logging
from typing import Optional, Union
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_TEXT_LIMIT = 4096


class TelegramClient:
    """Async Telegram Bot client for posting messages to a target channel."""

    def __init__(self, token: str, channel_id: Union[int, str]) -> None:
        """
        Initialize Telegram client.

        :param token: Bot API token from @BotFather
        :param channel_id: Target channel ID or username (e.g., -1001234567890 or @channel)
        """
        self.bot = Bot(token=token)
        self.channel_id = channel_id

    async def initialize(self) -> None:
        """Test API connectivity and bot validity."""
        try:
            bot_info = await self.bot.get_me()
            logger.info("Connected to Telegram as @%s (Bot ID: %s)", bot_info.username, bot_info.id)
        except Exception as e:
            logger.error("Failed to connect to Telegram Bot API: %s", e)
            raise

    async def send_text_message(self, text: str) -> Optional[int]:
        """
        Send plain text to Telegram channel.

        :param text: Text content
        :return: Telegram message ID if successful, None otherwise
        """
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
        """
        Upload photo file bytes to Telegram channel with caption.

        :param photo_bytes: Raw image file bytes
        :param caption: Photo caption
        :return: Telegram message ID if successful, None otherwise
        """
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
        """
        Upload video file bytes to Telegram channel with caption.

        :param video_bytes: Raw video file bytes
        :param caption: Video caption
        :return: Telegram message ID if successful, None otherwise
        """
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