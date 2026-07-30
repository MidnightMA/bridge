"""
Bale userbot client using aiobale library.
Manages user authentication, persistent sessions, message listening, and media extraction.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum, auto
import inspect
import logging
import os
from pathlib import Path
from typing import Callable, Awaitable, Optional, Union, Any

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

        sig = inspect.signature(Client.__init__)
        params = sig.parameters

        client_kwargs = {}
        if "dispatcher" in params:
            client_kwargs["dispatcher"] = self.dispatcher

        if "phone_number" in params and self.phone_number:
            client_kwargs["phone_number"] = self.phone_number

        for session_param in ("session_name", "session_file", "session_path", "name", "session_id"):
            if session_param in params:
                client_kwargs[session_param] = self.session_name
                break

        self.client = Client(**client_kwargs)

        self._message_callback: Optional[MessageHandlerCallback] = None
        self._is_running = False

    def set_message_handler(self, callback: MessageHandlerCallback) -> None:
        """Set async callback for processing normalized messages."""
        self._message_callback = callback

    async def authenticate_and_start(self) -> None:
        """Connect to Bale and verify user authentication."""
        self._register_event_handlers()

        try:
            if hasattr(self.client, "connect") and callable(getattr(self.client, "connect")):
                await self.client.connect()
            elif hasattr(self.client, "start") and callable(getattr(self.client, "start")):
                await self.client.start()

            logger.info("Connected to Bale")

            is_authorized = await self._check_auth_state()
            if not is_authorized:
                await self._perform_phone_login()

            logger.info("Logged in successfully")
            logger.info("Watching channel %s ...", self.target_channel_id)

        except Exception as e:
            logger.error("Authentication or connection error on Bale: %s", e)
            raise

    async def _check_auth_state(self) -> bool:
        """Check if session is currently authorized."""
        try:
            if hasattr(self.client, "is_user_authorized") and callable(getattr(self.client, "is_user_authorized")):
                return await self.client.is_user_authorized()
            if hasattr(self.client, "is_authorized") and callable(getattr(self.client, "is_authorized")):
                return await self.client.is_authorized()
            if hasattr(self.client, "get_me") and callable(getattr(self.client, "get_me")):
                me = await self.client.get_me()
                return me is not None
            if hasattr(self.client, "me") and self.client.me:
                return True
            return False
        except Exception:
            return False

    async def _perform_phone_login(self) -> None:
        """Prompt CLI interactive login if session file does not exist yet."""
        print("\n--- Bale User Account Authentication ---")
        phone = self.phone_number or input("Enter Bale Phone Number (+98...): ").strip()

        if hasattr(self.client, "start_phone_auth") and callable(getattr(self.client, "start_phone_auth")):
            auth_info = await self.client.start_phone_auth(phone)
            code = input("Enter verification code sent to Bale/SMS: ").strip()

            if hasattr(self.client, "sign_in") and callable(getattr(self.client, "sign_in")):
                await self.client.sign_in(phone=phone, code=code, auth_info=auth_info)
            elif hasattr(self.client, "complete_phone_auth") and callable(getattr(self.client, "complete_phone_auth")):
                await self.client.complete_phone_auth(code=code)
        elif hasattr(self.client, "start") and callable(getattr(self.client, "start")):
            await self.client.start()
        elif hasattr(self.client, "auth_cli") and callable(getattr(self.client, "auth_cli")):
            await self.client.auth_cli()

        logger.info("Authentication complete. Session saved.")

    def _register_event_handlers(self) -> None:
        """Register dispatcher handlers."""

        @self.dispatcher.message()
        async def _on_message(message: Message) -> None:
            await self._process_incoming_message(message)

    async def _process_incoming_message(self, message: Message) -> None:
        """Process raw update from Bale."""
        try:
            peer_id, chat_username = self._extract_peer_info(message)

            logger.info("Received update from peer_id: %s (Username: @%s)", peer_id, chat_username or "None")

            if not self._is_target_channel(peer_id, chat_username):
                logger.debug("Ignored update from peer_id %s (Target configured: %s)", peer_id, self.target_channel_id)
                return

            normalized = await self._normalize_message(message, peer_id)
            if normalized.msg_type == MessageType.UNSUPPORTED:
                return

            if self._message_callback:
                await self._message_callback(normalized)

        except Exception as e:
            logger.error("Error handling incoming message from Bale: %s", e, exc_info=True)

    def _extract_peer_info(self, message: Message) -> tuple[str, str]:
        """Extract chat/peer ID and username from Message object."""
        peer_id = ""
        username = ""

        if hasattr(message, "chat") and message.chat:
            peer_id = str(getattr(message.chat, "id", getattr(message.chat, "peer_id", "")))
            username = str(getattr(message.chat, "username", "") or "")
        elif hasattr(message, "peer_id") and message.peer_id:
            peer_id = str(message.peer_id)
        elif hasattr(message, "peer") and message.peer:
            peer_id = str(getattr(message.peer, "id", message.peer))

        return peer_id, username

    def _is_target_channel(self, peer_id: str, chat_username: str = "") -> bool:
        """Compare message peer with configured target channel with flexible matching."""
        target = self.target_channel_id.strip()
        peer = peer_id.strip()

        if not target:
            return False

        if target == peer:
            return True

        if chat_username and target.lstrip("@").lower() == chat_username.lstrip("@").lower():
            return True

        clean_target = target.removeprefix("-100").removeprefix("-").removeprefix("@")
        clean_peer = peer.removeprefix("-100").removeprefix("-").removeprefix("@")

        return clean_target and clean_peer and clean_target == clean_peer

    async def _normalize_message(self, message: Message, peer_id: str) -> NormalizedMessage:
        """Detect supported message types and download original media."""
        msg_id = getattr(message, "id", getattr(message, "message_id", 0))

        # Photo
        if self._is_photo(message):
            logger.info("New photo")
            caption = self._extract_text(message)
            media_bytes = await self._download_media(message, "photo")
            if media_bytes:
                logger.info("Successfully downloaded photo (%d bytes)", len(media_bytes))
            else:
                logger.warning("Could not download photo media bytes for message ID %s", msg_id)

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
            if media_bytes:
                logger.info("Successfully downloaded video (%d bytes)", len(media_bytes))
            else:
                logger.warning("Could not download video media bytes for message ID %s", msg_id)

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

        logger.info("Received message type that was not recognized as text, photo, or video.")
        self._log_message_debug(message)

        return NormalizedMessage(
            message_id=msg_id,
            peer_id=peer_id,
            msg_type=MessageType.UNSUPPORTED,
        )

    def _log_message_debug(self, message: Message) -> None:
        """Helper to log attributes of unrecognized messages for troubleshooting."""
        attrs = {}
        for key in ("photo", "photos", "video", "document", "file", "media", "content", "type", "content_type", "text", "caption"):
            val = getattr(message, key, None)
            if val is not None:
                attrs[key] = str(val)[:200]
        logger.info("Message debug attributes: %s", attrs)

    @staticmethod
    def _is_photo(message: Message) -> bool:
        """Check if message contains a photo."""
        if getattr(message, "photo", None) or getattr(message, "photos", None):
            return True

        content = getattr(message, "content", None)
        if content and (getattr(content, "photo", None) or getattr(content, "photos", None)):
            return True

        media = getattr(message, "media", None) or getattr(message, "attachment", None)
        if media and (getattr(media, "photo", None) or getattr(media, "type", "") in ("photo", "image")):
            return True

        doc = getattr(message, "document", None) or getattr(message, "file", None)
        if doc:
            mime = getattr(doc, "mime_type", "") or getattr(doc, "mimetype", "") or ""
            name = getattr(doc, "file_name", "") or getattr(doc, "name", "") or ""
            if mime.startswith("image/") or name.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic")):
                return True

        msg_type = str(getattr(message, "content_type", "") or getattr(message, "type", "")).lower()
        if "photo" in msg_type or "image" in msg_type:
            return True

        return False

    @staticmethod
    def _is_video(message: Message) -> bool:
        """Check if message contains a video."""
        if getattr(message, "video", None) or getattr(message, "animation", None):
            return True

        content = getattr(message, "content", None)
        if content and (getattr(content, "video", None) or getattr(content, "animation", None)):
            return True

        media = getattr(message, "media", None) or getattr(message, "attachment", None)
        if media and (getattr(media, "video", None) or getattr(media, "type", "") in ("video", "animation")):
            return True

        doc = getattr(message, "document", None) or getattr(message, "file", None)
        if doc:
            mime = getattr(doc, "mime_type", "") or getattr(doc, "mimetype", "") or ""
            name = getattr(doc, "file_name", "") or getattr(doc, "name", "") or ""
            if mime.startswith("video/") or name.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
                return True

        msg_type = str(getattr(message, "content_type", "") or getattr(message, "type", "")).lower()
        if "video" in msg_type or "animation" in msg_type:
            return True

        return False

    @staticmethod
    def _is_plain_text(message: Message) -> bool:
        """Check if message is plain text without media attachments."""
        media_attrs = (
            "photo", "photos", "video", "sticker", "voice", "audio",
            "document", "file", "media", "attachment", "location",
            "contact", "poll", "gift"
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
        candidates = []

        # 1. Photo objects (if list/tuple, select highest resolution [-1])
        photo_attr = getattr(message, "photo", None) or getattr(message, "photos", None)
        if photo_attr:
            if isinstance(photo_attr, (list, tuple)) and len(photo_attr) > 0:
                candidates.append(photo_attr[-1])
            else:
                candidates.append(photo_attr)

        # 2. Content photo
        content = getattr(message, "content", None)
        if content:
            c_photo = getattr(content, "photo", None) or getattr(content, "photos", None)
            if c_photo:
                if isinstance(c_photo, (list, tuple)) and len(c_photo) > 0:
                    candidates.append(c_photo[-1])
                else:
                    candidates.append(c_photo)

        # 3. Video objects
        video_attr = getattr(message, "video", None)
        if video_attr:
            candidates.append(video_attr)

        # 4. Document or file attribute
        doc_attr = getattr(message, "document", None) or getattr(message, "file", None)
        if doc_attr:
            candidates.append(doc_attr)

        # 5. Message object itself
        candidates.append(message)

        for target in candidates:
            # Method A: target.download()
            if hasattr(target, "download") and callable(getattr(target, "download")):
                try:
                    res = await target.download()
                    data = self._resolve_download_result(res)
                    if data:
                        return data
                except Exception as e:
                    logger.debug("Candidate .download() failed: %s", e)

            # Method B: client.download_media(target)
            if hasattr(self.client, "download_media") and callable(getattr(self.client, "download_media")):
                try:
                    res = await self.client.download_media(target)
                    data = self._resolve_download_result(res)
                    if data:
                        return data
                except Exception as e:
                    logger.debug("client.download_media() failed: %s", e)

            # Method C: client.download_file(target)
            if hasattr(self.client, "download_file") and callable(getattr(self.client, "download_file")):
                try:
                    res = await self.client.download_file(target)
                    data = self._resolve_download_result(res)
                    if data:
                        return data
                except Exception as e:
                    logger.debug("client.download_file() failed: %s", e)

        logger.error("Could not download %s media: all download strategies failed.", media_kind)
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
                if hasattr(self.client, "run_until_disconnected") and callable(getattr(self.client, "run_until_disconnected")):
                    await self.client.run_until_disconnected()
                elif hasattr(self.client, "run") and callable(getattr(self.client, "run")):
                    await self.client.run()
                elif hasattr(self.client, "idle") and callable(getattr(self.client, "idle")):
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
            if hasattr(self.client, "disconnect") and callable(getattr(self.client, "disconnect")):
                await self.client.disconnect()
            elif hasattr(self.client, "stop") and callable(getattr(self.client, "stop")):
                await self.client.stop()
            elif hasattr(self.client, "close") and callable(getattr(self.client, "close")):
                await self.client.close()
            logger.info("Bale client stopped.")
        except Exception as e:
            logger.warning("Error stopping Bale client: %s", e)