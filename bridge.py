"""
Bridge module routing messages from Bale client to Telegram client.
Prevents duplicate posts using a bounded in-memory cache.
"""

from collections import deque
import logging
from typing import Set, Union

from bale_client import BaleClient, NormalizedMessage, MessageType
from telegram_client import TelegramClient

logger = logging.getLogger(__name__)

MAX_DEDUP_SIZE = 5000


class MessageBridge:
    """Connects Bale event updates to Telegram publishing logic."""

    def __init__(self, bale_client: BaleClient, telegram_client: TelegramClient) -> None:
        """
        Initialize bridge.

        :param bale_client: Initialized Bale userbot client
        :param telegram_client: Initialized Telegram Bot client
        """
        self.bale_client = bale_client
        self.telegram_client = telegram_client

        self._processed_set: Set[Union[str, int]] = set()
        self._processed_queue: deque = deque()

        # Connect message callback
        self.bale_client.set_message_handler(self.on_bale_message)

    def _is_duplicate(self, msg_id: Union[str, int]) -> bool:
        """Check if message ID has already been forwarded."""
        return msg_id in self._processed_set

    def _mark_processed(self, msg_id: Union[str, int]) -> None:
        """Add message ID to deduplication cache."""
        if msg_id in self._processed_set:
            return

        self._processed_set.add(msg_id)
        self._processed_queue.append(msg_id)

        if len(self._processed_queue) > MAX_DEDUP_SIZE:
            oldest = self._processed_queue.popleft()
            self._processed_set.discard(oldest)

    async def on_bale_message(self, msg: NormalizedMessage) -> None:
        """
        Handle normalized incoming message from Bale channel.

        :param msg: NormalizedMessage object
        """
        msg_id = msg.message_id

        if self._is_duplicate(msg_id):
            logger.info("Skipping duplicate message (ID: %s)", msg_id)
            return

        success = False

        if msg.msg_type == MessageType.TEXT and msg.text:
            tg_id = await self.telegram_client.send_text_message(text=msg.text)
            if tg_id:
                success = True

        elif msg.msg_type == MessageType.PHOTO and msg.media_bytes:
            tg_id = await self.telegram_client.send_photo_message(
                photo_bytes=msg.media_bytes,
                caption=msg.caption,
            )
            if tg_id:
                success = True

        elif msg.msg_type == MessageType.VIDEO and msg.media_bytes:
            tg_id = await self.telegram_client.send_video_message(
                video_bytes=msg.media_bytes,
                caption=msg.caption,
            )
            if tg_id:
                success = True

        if success:
            self._mark_processed(msg_id)
            logger.info("Forwarded successfully")
        else:
            logger.error("Failed to forward message ID %s to Telegram.", msg_id)