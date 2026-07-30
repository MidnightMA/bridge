"""
Message processing handler containing filtering, deduplication, and routing logic.
"""

import logging
import time
from typing import Any, Optional, Set

from media import MediaManager
from telegram_client import TelegramClient

logger = logging.getLogger(__name__)


class MessageHandler:
    """Processes, filters, downloads, and forwards incoming channel messages."""

    def __init__(
        self,
        telegram_client: TelegramClient,
        media_manager: MediaManager,
        startup_timestamp: Optional[float] = None
    ) -> None:
        self.telegram_client = telegram_client
        self.media_manager = media_manager
        self.startup_timestamp = startup_timestamp or time.time()
        self.processed_msg_ids: Set[str] = set()

    def _extract_id(self, message: Any) -> str:
        """Extracts unique Message ID identifier string."""
        msg_id = getattr(message, "id", None) or getattr(message, "message_id", None)
        peer_id = getattr(message, "chat_id", None) or getattr(message, "peer_id", None)
        return f"{peer_id}_{msg_id}" if msg_id and peer_id else str(id(message))

    def _extract_date(self, message: Any) -> Optional[float]:
        """Extracts creation date timestamp from message if available."""
        date_val = getattr(message, "date", None) or getattr(message, "timestamp", None)
        if isinstance(date_val, (int, float)):
            return float(date_val)
        if hasattr(date_val, "timestamp"):
            return date_val.timestamp()
        return None

    async def process_message(self, message: Any) -> None:
        """Core message processing handler."""
        msg_id = self._extract_id(message)

        # 1. Deduplication check
        if msg_id in self.processed_msg_ids:
            logger.debug(f"Skipping duplicate message: {msg_id}")
            return

        # 2. Never resend old messages created before startup
        msg_date = self._extract_date(message)
        if msg_date and msg_date < self.startup_timestamp:
            logger.info(f"Skipping pre-existing historical message: {msg_id}")
            self.processed_msg_ids.add(msg_id)
            return

        # Inspect Message Content
        text = str(getattr(message, "text", "") or getattr(message, "message", "") or "")
        caption = str(getattr(message, "caption", "") or getattr(message, "caption_text", "") or text)

        has_photo = getattr(message, "photo", None) is not None or getattr(message, "is_photo", False)
        has_video = getattr(message, "video", None) is not None or getattr(message, "is_video", False)

        # Reject all other types (voice, audio, documents, stickers)
        has_voice = getattr(message, "voice", None) is not None
        has_audio = getattr(message, "audio", None) is not None
        has_doc = getattr(message, "document", None) is not None and not (has_photo or has_video)
        has_sticker = getattr(message, "sticker", None) is not None

        if has_voice or has_audio or has_doc or has_sticker:
            logger.info(f"Ignoring unsupported message type for message ID: {msg_id}")
            self.processed_msg_ids.add(msg_id)
            return

        success = False

        try:
            # Handle Photo
            if has_photo:
                filename = f"photo_{msg_id}.jpg"
                async with self.media_manager.temp_file_scope(filename) as temp_path:
                    if hasattr(message, "download"):
                        await message.download(file_name=str(temp_path))
                    elif hasattr(message, "download_media"):
                        await message.download_media(file=str(temp_path))

                    if temp_path.exists():
                        success = await self.telegram_client.send_photo(
                            photo_path=temp_path,
                            caption=caption if caption else None
                        )
                    else:
                        logger.error(f"Failed to save photo for message: {msg_id}")

            # Handle Video
            elif has_video:
                filename = f"video_{msg_id}.mp4"
                async with self.media_manager.temp_file_scope(filename) as temp_path:
                    if hasattr(message, "download"):
                        await message.download(file_name=str(temp_path))
                    elif hasattr(message, "download_media"):
                        await message.download_media(file=str(temp_path))

                    if temp_path.exists():
                        success = await self.telegram_client.send_video(
                            video_path=temp_path,
                            caption=caption if caption else None
                        )
                    else:
                        logger.error(f"Failed to save video for message: {msg_id}")

            # Handle Plain Text
            elif text:
                success = await self.telegram_client.send_text(text)

            else:
                logger.info(f"Message {msg_id} contained no readable supported content. Ignored.")
                self.processed_msg_ids.add(msg_id)
                return

            if success:
                logger.info(f"Successfully processed and mirrored message {msg_id}")
                self.processed_msg_ids.add(msg_id)
            else:
                logger.warning(f"Failed to forward message {msg_id} to Telegram. App remains active.")

        except Exception as e:
            logger.error(f"Unhandled error processing message {msg_id}: {e}", exc_info=True)
            self.processed_msg_ids.add(msg_id)