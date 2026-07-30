"""Forwarding pipeline and SQLite deduplication engine."""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional
import aiohttp

from downloader import Downloader
from telegram_client import TelegramClient

logger = logging.getLogger("bridge.forwarder")


class MessageDeduplicator:
    """Persistent SQLite store to prevent duplicate message forwarding."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Creates the database table if it does not exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forwarded_messages (
                    message_id TEXT PRIMARY KEY,
                    forwarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

    def is_processed(self, message_id: str) -> bool:
        """Checks if a message ID has already been forwarded."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM forwarded_messages WHERE message_id = ?",
                (str(message_id),),
            )
            return cursor.fetchone() is not None

    def mark_processed(self, message_id: str) -> None:
        """Marks a message ID as successfully processed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO forwarded_messages (message_id) VALUES (?)",
                (str(message_id),),
            )
            conn.commit()


class MessageForwarder:
    """Core pipeline for processing, downloading, and forwarding messages to Telegram."""

    def __init__(
        self,
        telegram_client: TelegramClient,
        downloader: Downloader,
        db_path: Path,
    ) -> None:
        self.telegram_client = telegram_client
        self.downloader = downloader
        self.deduplicator = MessageDeduplicator(db_path)

    async def process_message(self, message_data: Dict[str, Any]) -> bool:
        """Processes a single incoming message from Bale.

        Args:
            message_data: Standardized message dictionary containing:
                - id (str)
                - type ('text' | 'photo' | 'video')
                - text (str | None)
                - media_url (str | None)
                - caption (str | None)

        Returns:
            bool: True if message was successfully processed and sent, False otherwise.
        """
        msg_id = str(message_data.get("id", ""))
        msg_type = message_data.get("type")

        if not msg_id:
            logger.warning("Received message update missing ID. Skipping.")
            return False

        if self.deduplicator.is_processed(msg_id):
            logger.debug(f"Message ID {msg_id} already processed. Skipping duplicate.")
            return False

        if msg_type not in ("text", "photo", "video"):
            logger.debug(f"Ignoring unsupported message type '{msg_type}' for ID {msg_id}.")
            return False

        logger.info(f"Processing incoming '{msg_type}' message (ID: {msg_id})...")
        temp_file: Optional[Path] = None

        try:
            # 1. Text Message Forwarding
            if msg_type == "text":
                text = message_data.get("text")
                if not text:
                    logger.warning(f"Text message ID {msg_id} has empty content. Skipping.")
                    return False
                await self.telegram_client.send_text(text)

            # 2. Photo Message Forwarding
            elif msg_type == "photo":
                media_url = message_data.get("media_url")
                caption = message_data.get("caption")
                if not media_url:
                    logger.warning(f"Photo message ID {msg_id} missing media_url. Skipping.")
                    return False

                async with aiohttp.ClientSession() as session:
                    temp_file = await self.downloader.download_file(
                        media_url, session, file_extension=".jpg"
                    )

                await self.telegram_client.send_photo(temp_file, caption=caption)

            # 3. Video Message Forwarding
            elif msg_type == "video":
                media_url = message_data.get("media_url")
                caption = message_data.get("caption")
                if not media_url:
                    logger.warning(f"Video message ID {msg_id} missing media_url. Skipping.")
                    return False

                async with aiohttp.ClientSession() as session:
                    temp_file = await self.downloader.download_file(
                        media_url, session, file_extension=".mp4"
                    )

                await self.telegram_client.send_video(temp_file, caption=caption)

            # Mark as processed in SQLite database only upon successful delivery
            self.deduplicator.mark_processed(msg_id)
            logger.info(f"Successfully forwarded message ID {msg_id} to Telegram channel.")
            return True

        except Exception as e:
            logger.error(f"Failed to forward message ID {msg_id} to Telegram: {e}", exc_info=True)
            return False

        finally:
            if temp_file:
                self.downloader.cleanup_file(temp_file)