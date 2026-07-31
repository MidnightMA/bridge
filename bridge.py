"""
Bridge module routing messages from Bale client to Telegram client.
Supports single messages, album grouping (media groups), and deduplication.
"""

import asyncio
from collections import deque
import logging
from typing import Dict, List, Set, Union

from bale_client import BaleClient, NormalizedMessage, MessageType
from telegram_client import TelegramClient

logger = logging.getLogger(__name__)

MAX_DEDUP_SIZE = 5000
ALBUM_DEBOUNCE_DELAY = 1.2  # Seconds window to accumulate album items


class MessageBridge:
    """Connects Bale event updates to Telegram publishing logic with album support."""

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

        # Album debouncer buffer
        self._album_buffers: Dict[str, List[NormalizedMessage]] = {}
        self._album_tasks: Dict[str, asyncio.Task] = {}

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

        # Plain text messages
        if msg.msg_type == MessageType.TEXT and msg.text:
            tg_id = await self.telegram_client.send_text_message(text=msg.text)
            if tg_id:
                self._mark_processed(msg_id)
                logger.info("Forwarded text successfully")
            return

        # Media items (PHOTO or VIDEO) -> Album Debouncer
        if msg.msg_type in (MessageType.PHOTO, MessageType.VIDEO) and msg.media_bytes:
            await self._enqueue_media_item(msg)

    async def _enqueue_media_item(self, msg: NormalizedMessage) -> None:
        """Buffer media item to group albums or send individually."""
        group_key = msg.media_group_id or f"peer_{msg.peer_id}"

        if group_key not in self._album_buffers:
            self._album_buffers[group_key] = []

        self._album_buffers[group_key].append(msg)

        # Reset timer window for this album
        if group_key in self._album_tasks and not self._album_tasks[group_key].done():
            self._album_tasks[group_key].cancel()

        self._album_tasks[group_key] = asyncio.create_task(
            self._flush_album_after_delay(group_key)
        )

    async def _flush_album_after_delay(self, group_key: str) -> None:
        """Wait debounce window, then flush buffered media items to Telegram."""
        try:
            await asyncio.sleep(ALBUM_DEBOUNCE_DELAY)
        except asyncio.CancelledError:
            return

        items = self._album_buffers.pop(group_key, [])
        self._album_tasks.pop(group_key, None)

        if not items:
            return

        media_items = [
            {
                "type": item.msg_type,
                "bytes": item.media_bytes,
                "caption": item.caption,
                "msg_id": item.message_id,
            }
            for item in items
        ]

        if len(media_items) == 1:
            # Single photo or video
            single = media_items[0]
            success = False

            if single["type"] == MessageType.PHOTO:
                tg_id = await self.telegram_client.send_photo_message(
                    photo_bytes=single["bytes"],
                    caption=single["caption"],
                )
                if tg_id:
                    success = True
            elif single["type"] == MessageType.VIDEO:
                tg_id = await self.telegram_client.send_video_message(
                    video_bytes=single["bytes"],
                    caption=single["caption"],
                )
                if tg_id:
                    success = True

            if success:
                self._mark_processed(single["msg_id"])
                logger.info("Forwarded single media successfully")
        else:
            # Album (media group)
            tg_ids = await self.telegram_client.send_media_group(media_items)
            if tg_ids:
                for item in items:
                    self._mark_processed(item.message_id)
                logger.info("Forwarded album (%d media items) successfully", len(media_items))