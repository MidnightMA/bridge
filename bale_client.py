"""
Bale userbot client using aiobale library.
Manages user authentication, persistent sessions, message listening, and media extraction.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum, auto
import logging
import os
from pathlib import Path
from typing import Callable, Awaitable, Optional, Union

from aiobale import Client, Dispatcher
from aiobale.types import Message

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Supported message categories."""
    TEXT = auto()
    PHOTO = auto()
    VIDEO = auto()
    UNSUPPORTED = auto()


@dataclass
class NormalizedMessage:
    """Clean data representation of incoming Bale messages."""
    message_id: Union[str, int]
    peer_id: Union[str, int]
    msg_type: MessageType
    text: Optional[str] = None
    caption: Optional[str] = None
    media_bytes: Optional[bytes] = None


MessageHandlerCallback = Callable[[NormalizedMessage], Awaitable[None]]


class BaleClient:
    """Userbot client using aiobale to interact with Bale internal API."""

    def __init__(
        self,
        phone_number: str,
        session_name: str = "bale_session",
        target_channel_id: Union[str, int] = "",
    ) -> None:
        """
        Initialize Bale userbot client.

        :param phone_number: Account phone number
        :param session_name: Name of the session storage file
        :param target_channel_id: Channel ID or handle to monitor
        """
        self.phone_number = phone_number
        self.session_name = session_name
        self.target_channel_id = str(target_channel_id)

        self.dispatcher = Dispatcher()
        self.client = Client(
            session=self.session_name,
            # phone_number=self.phone_number,
            dispatcher=self.dispatcher,
        )

        self._message_callback: Optional[MessageHandlerCallback] = None
        self._is_running = False

    def set_message_handler(self, callback: MessageHandlerCallback) -> None:
        """Set async callback for processing normalized messages."""
        self._message_callback = callback

    async def authenticate_and_start() -> None:
        """
        Connect to Bale, verify/perform user account authentication, and start watching.
        """
        self._register_event_handlers()

        try:
            await self.client.connect()
            logger.info("Connected to Bale")

            is_authorized = await self._check_auth_state()
            if not is_authorized:
                await self._perform_phone_login()

            logger.info("Logged in successfully")
            logger.info("Watching channel %s ...", self.target_channel_id)

        except Exception as e:
            logger.error("Authentication or connection error on Bale: %s", e)
            raise

    async def _check_auth_state() -> bool:
        """Check if session is currently authorized."""
        try:
            if hasattr(self.client, "is_user_authorized"):
                return await self.client.is_user_authorized()
            if hasattr(self.client, "me") and self.client.me:
                return True
            if hasattr(self.client, "get_me"):
                me = await self.client.get_me()
                return me is not None
            return False
        except Exception:
            return False

    async def _perform_phone_login(self) -> None:
        """Prompt CLI interactive login if session file does not exist yet."""
        print("\n--- Bale User Account Authentication ---")
        phone = self.phone_number or input("Enter Bale Phone Number (+98...): ").strip()

        if hasattr(self.client, "start_phone_auth"):
            auth_info = await self.client.start_phone_auth(phone)
            code = input("Enter verification code sent to Bale/SMS: ").strip()

            if hasattr(self.client, "sign_in"):
                await self.client.sign_in(phone=phone, code=code, auth_info=auth_info)
            elif hasattr(self.client, "complete_phone_auth"):
                await self.client.complete_phone_auth(code=code)
        elif hasattr(self.client, "auth_cli"):
            await self.client.auth_cli()
        else:
            await self.client.start()

        logger.info("Authentication complete. Session saved to %s", self.session_name)

    def _register_event_handlers(self) -> None:
        """Register dispatcher handlers."""

        @self.dispatcher.message()
        async def _on_message(message: Message) -> None:
            await self._process_incoming_message(message)

    async def _process_incoming_message(self, message: Message) -> None:
        """Process raw update from Bale."""
        try:
            peer_id = self._extract_peer_id(message)

            if not self._is_target_channel(peer_id):
                return

            normalized = await self._normalize_message(message, peer_id)
            if normalized.msg_type == MessageType.UNSUPPORTED:
                return

            if self._message_callback:
                await self._message_callback(normalized)

        except Exception as e:
            logger.error("Error handling incoming message from Bale: %s", e, exc_info=True)

    def _extract_peer_id(self, message: Message) -> str:
        """Extract chat/peer ID from Message object."""
        if hasattr(message, "chat") and message.chat:
            return str(getattr(message.chat, "id", getattr(message.chat, "peer_id", "")))
        if hasattr(message, "peer_id") and message.peer_id:
            return str(message.peer_id)
        if hasattr(message, "peer") and message.peer:
            return str(getattr(message.peer, "id", message.peer))
        return ""

    def _is_target_channel(self, peer_id: str) -> bool:
        """Compare message peer with configured target channel."""
        target = self.target_channel_id.strip()
        peer = peer_id.strip()

        if not target or not peer:
            return False

        if target == peer:
            return True

        # Normalize prefix variations (-100..., @...)
        clean_target = target.removeprefix("-100").removeprefix("@")
        clean_peer = peer.removeprefix("-100").removeprefix("@")
        return clean_target == clean_peer

    async def _normalize_message(self, message: Message, peer_id: str) -> NormalizedMessage:
        """Detect supported message types and download original media."""
        msg_id = getattr(message, "id", getattr(message, "message_id", 0))

        # Photo
        if self._is_photo(message):
            logger.info("New photo")
            caption = self._extract_text(message)
            media_bytes = await self._download_media(message, "photo")
            return NormalizedMessage(
                message_id=msg_id,
                peer_id=peer_id,
                msg_type=MessageType.PHOTO if media_bytes else MessageType.UNSUPPORTED,
                caption=caption,
                media_bytes=media_bytes,
            )

        # Video
        if self._is_video(message):
            logger.info("New video")
            caption = self._extract_text(message)
            media_bytes = await self._download_media(message, "video")
            return NormalizedMessage(
                message_id=msg_id,
                peer_id=peer_id,
                msg_type=MessageType.VIDEO if media_bytes else MessageType.UNSUPPORTED,
                caption=caption,
                media_bytes=media_bytes,
            )

        # Plain Text
        if self._is_plain_text(message):
            logger.info("New text message")
            text = self._extract_text(message)
            return NormalizedMessage(
                message_id=msg_id,
                peer_id=peer_id,
                msg_type=MessageType.TEXT,
                text=text,
            )

        # Ignored types (sticker, voice, document, location, poll, etc.)
        return NormalizedMessage(
            message_id=msg_id,
            peer_id=peer_id,
            msg_type=MessageType.UNSUPPORTED,
        )

    @staticmethod
    def _is_photo(message: Message) -> bool:
        """Check if message contains a photo."""
        if getattr(message, "photo", None):
            return True
        if hasattr(message, "content") and getattr(message.content, "photo", None):
            return True
        return False

    @staticmethod
    def _is_video(message: Message) -> bool:
        """Check if message contains a video."""
        if getattr(message, "video", None):
            return True
        if hasattr(message, "content") and getattr(message.content, "video", None):
            return True
        return False

    @staticmethod
    def _is_plain_text(message: Message) -> bool:
        """Check if message is plain text without media attachments."""
        media_attrs = (
            "photo", "video", "sticker", "voice", "audio",
            "document", "location", "contact", "poll", "gift"
        )
        for attr in media_attrs:
            if getattr(message, attr, None):
                return False
            if hasattr(message, "content") and getattr(message.content, attr, None):
                return False

        text = getattr(message, "text", None) or getattr(message, "caption", None)
        return bool(text and text.strip())

    @staticmethod
    def _extract_text(message: Message) -> str:
        """Extract text or caption from message."""
        text = getattr(message, "caption", None) or getattr(message, "text", None)
        if not text and hasattr(message, "content"):
            text = getattr(message.content, "text", None) or getattr(message.content, "caption", None)
        return text.strip() if text else ""

    async def _download_media(self, message: Message, media_kind: str) -> Optional[bytes]:
        """Download media file into memory using fallbacks."""
        try:
            # 1. message.download()
            if hasattr(message, "download") and callable(message.download):
                res = await message.download()
                return self._resolve_download_result(res)

            # 2. photo/video object download
            media_obj = getattr(message, media_kind, None)
            if media_obj and hasattr(media_obj, "download") and callable(media_obj.download):
                res = await media_obj.download()
                return self._resolve_download_result(res)

            # 3. client.download_media()
            if hasattr(self.client, "download_media"):
                res = await self.client.download_media(message)
                return self._resolve_download_result(res)

            logger.error("Could not find download method for %s", media_kind)
            return None

        except Exception as e:
            logger.error("Failed to download %s media: %s", media_kind, e)
            return None

    @staticmethod
    def _resolve_download_result(result: Union[bytes, str, Path]) -> Optional[bytes]:
        """Convert download result (file path or bytes) to byte array."""
        if isinstance(result, bytes):
            return result
        if isinstance(result, (str, Path)) and os.path.exists(result):
            with open(result, "rb") as f:
                data = f.read()
            os.remove(result)
            return data
        return None

    async def run_forever(self) -> None:
        """Keep listening with automatic reconnection logic."""
        self._is_running = True
        while self._is_running:
            try:
                if hasattr(self.client, "run_until_disconnected"):
                    await self.client.run_until_disconnected()
                elif hasattr(self.client, "idle"):
                    await self.client.idle()
                else:
                    while self._is_running:
                        await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._is_running:
                    break
                logger.warning("Disconnected from Bale: %s", e)
                logger.info("Reconnect...")
                await asyncio.sleep(5)
                try:
                    await self.authenticate_and_start()
                except Exception as rec_err:
                    logger.error("Reconnection failed: %s", rec_err)

    async def stop(self) -> None:
        """Stop Bale connection gracefully."""
        self._is_running = False
        try:
            if hasattr(self.client, "disconnect"):
                await self.client.disconnect()
            elif hasattr(self.client, "stop"):
                await self.client.stop()
            elif hasattr(self.client, "close"):
                await self.client.close()
            logger.info("Bale client stopped.")
        except Exception as e:
            logger.warning("Error stopping Bale client: %s", e)