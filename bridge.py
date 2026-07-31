"""
Bridge module routing messages from Bale client to Telegram client.
Includes album/media group aggregator and deduplication.
"""

import asyncio
from collections import deque
import logging
from typing import Dict, List, Set, Union, Tuple, Any

from bale_client import BaleClient, NormalizedMessage, MessageType
from telegram_client import TelegramClient

logger = logging.getLogger(__name__)

MAX_DEDUP_SIZE = 5000
ALBUM_BUFFER_DELAY = 1.8  # Buffer wait time in seconds to aggregate album items


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

        # Buffer for grouping media into albums: key -> (peer_id, grouped_id)
        self._album_buffers: Dict[Tuple[str, Any], List[NormalizedMessage]] = {}
        self._album_tasks: Dict[Tuple[str, Any], asyncio.Task] = {}

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

        # Plain Text messages -> send immediately
        if msg.msg_type == MessageType.TEXT:
            if msg.text:
                tg_id = await self.telegram_client.send_text_message(text=msg.text)
                if tg_id:
                    self._mark_processed(msg_id)
                    logger.info("Forwarded successfully")
            return

        # Photo or Video -> route through album aggregator buffer
        if msg.msg_type in (MessageType.PHOTO, MessageType.VIDEO):
            await self._buffer_media_item(msg)

    async def _buffer_media_item(self, msg: NormalizedMessage) -> None:
        """Add photo or video to buffer and schedule/reschedule album flush."""
        peer_id = str(msg.peer_id)
        gid = msg.grouped_id if msg.grouped_id is not None else "media_group"
        group_key = (peer_id, gid)

        if group_key not in self._album_buffers:
            self._album_buffers[group_key] = []

        self._album_buffers[group_key].append(msg)
        logger.info(
            "Buffered media item %s for album group %s (Total buffered: %d)",
            msg.message_id, group_key, len(self._album_buffers[group_key])
        )

        # Restart timer task for this group
        if group_key in self._album_tasks:
            self._album_tasks[group_key].cancel()

        self._album_tasks[group_key] = asyncio.create_task(
            self._flush_album_after_delay(group_key)
        )

    async def _flush_album_after_delay(self, group_key: Tuple[str, Any]) -> None:
        """Wait for buffer delay window, then send items as an album or single post."""
        try:
            await asyncio.sleep(ALBUM_BUFFER_DELAY)

            items = self._album_buffers.pop(group_key, [])
            self._album_tasks.pop(group_key, None)

            if not items:
                return

            logger.info("Flushing album group %s (%d media items)", group_key, len(items))

            success = await self.telegram_client.send_media_group_message(items)
            if success:
                for item in items:
                    self._mark_processed(item.message_id)
                logger.info("Forwarded successfully")
            else:
                logger.error("Failed to forward album items for group %s", group_key)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error flushing album group %s: %s", group_key, e, exc_info=True)