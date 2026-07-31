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
    DOCUMENT = auto()
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
    grouped_id: Optional[Union[str, int]] = None
    file_name: Optional[str] = None


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

    @staticmethod
    def _extract_grouped_id(message: Message) -> Optional[Union[str, int]]:
        """Extract album / media group ID if present."""
        return (
            getattr(message, "grouped_id", None)
            or getattr(message, "media_group_id", None)
            or getattr(message, "group_id", None)
            or getattr(getattr(message, "content", None), "grouped_id", None)
            or getattr(getattr(message, "content", None), "media_group_id", None)
        )

    @classmethod
    def _extract_file_name(cls, message: Message) -> Optional[str]:
        """Extract original filename from DocumentMessage if available."""
        docs = cls._find_documents_and_media(message)
        for doc_obj, _, _ in docs:
            name = (
                getattr(doc_obj, "file_name", None)
                or getattr(doc_obj, "name", None)
                or getattr(doc_obj, "filename", None)
            )
            if name and str(name).strip():
                return str(name).strip()
        return None

    async def _normalize_message(self, message: Message, peer_id: str) -> NormalizedMessage:
        """Detect supported message types and download original media."""
        msg_id = getattr(message, "id", getattr(message, "message_id", 0))
        grouped_id = self._extract_grouped_id(message)

        # Photo
        if self._is_photo(message):
            logger.info("New photo")
            caption = self._extract_text(message) or None
            if caption:
                logger.info("Extracted photo caption: '%s'", caption)

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
                grouped_id=grouped_id,
            )

        # Video
        if self._is_video(message):
            logger.info("New video")
            caption = self._extract_text(message) or None
            if caption:
                logger.info("Extracted video caption: '%s'", caption)

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
                grouped_id=grouped_id,
            )

        # Document / File
        if self._has_document_or_file(message):
            logger.info("New document/file")
            caption = self._extract_text(message) or None
            file_name = self._extract_file_name(message)
            if caption:
                logger.info("Extracted file caption: '%s'", caption)

            media_bytes = await self._download_media(message, "document")
            if media_bytes:
                logger.info("Successfully downloaded document/file (%d bytes)", len(media_bytes))
            else:
                logger.warning("Could not download document media bytes for message ID %s", msg_id)

            return NormalizedMessage(
                message_id=msg_id,
                peer_id=peer_id,
                msg_type=MessageType.DOCUMENT if media_bytes else MessageType.UNSUPPORTED,
                caption=caption,
                media_bytes=media_bytes,
                grouped_id=grouped_id,
                file_name=file_name,
            )

        # Plain Text
        if self._is_plain_text(message):
            logger.info("New text message")
            text = self._extract_text(message) or None
            return NormalizedMessage(
                message_id=msg_id,
                peer_id=peer_id,
                msg_type=MessageType.TEXT,
                text=text,
            )

        logger.info("Received message type that was not recognized as text, photo, video, or file.")

        return NormalizedMessage(
            message_id=msg_id,
            peer_id=peer_id,
            msg_type=MessageType.UNSUPPORTED,
        )

    @classmethod
    def _find_documents_and_media(cls, obj: Any, max_depth: int = 4) -> list[tuple[Any, Any, Any]]:
        """
        Recursively search obj for DocumentMessage or Media objects containing file_id and access_hash.
        Returns list of tuples: (doc_object, file_id, access_hash)
        """
        results = []
        visited = set()

        def _walk(current: Any, depth: int):
            if current is None or depth > max_depth or id(current) in visited:
                return
            visited.add(id(current))

            file_id = getattr(current, "file_id", None)
            access_hash = getattr(current, "access_hash", None)
            if file_id is not None and access_hash is not None:
                results.append((current, file_id, access_hash))

            attrs_to_check = (
                "document", "photo", "photos", "video", "content",
                "replied_to", "quoted_replied_to", "previous_message",
                "message", "media", "attachment", "file"
            )
            for attr in attrs_to_check:
                val = getattr(current, attr, None)
                if val is not None:
                    if isinstance(val, (list, tuple)):
                        for item in val:
                            _walk(item, depth + 1)
                    else:
                        _walk(val, depth + 1)

        _walk(obj, 0)
        return results

    @classmethod
    def _has_document_or_file(cls, message: Message) -> bool:
        """Check if message contains any document or file attachment."""
        docs = cls._find_documents_and_media(message)
        return len(docs) > 0

    @classmethod
    def _is_photo(cls, message: Message) -> bool:
        """Check if message or its nested/forwarded content contains a photo."""
        docs = cls._find_documents_and_media(message)
        for doc_obj, _, _ in docs:
            mime = str(getattr(doc_obj, "mime_type", "") or getattr(doc_obj, "mimetype", "") or "").lower()
            name = str(getattr(doc_obj, "file_name", "") or getattr(doc_obj, "name", "") or "").lower()
            if mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic")):
                return True

        msg_str = str(message).lower()
        if "documentmessage" in msg_str and ("image/" in msg_str or ".jpg" in msg_str or ".png" in msg_str or ".jpeg" in msg_str):
            return True

        return False

    @classmethod
    def _is_video(cls, message: Message) -> bool:
        """Check if message or its nested/forwarded content contains a video."""
        docs = cls._find_documents_and_media(message)
        for doc_obj, _, _ in docs:
            mime = str(getattr(doc_obj, "mime_type", "") or getattr(doc_obj, "mimetype", "") or "").lower()
            name = str(getattr(doc_obj, "file_name", "") or getattr(doc_obj, "name", "") or "").lower()
            if mime.startswith("video/") or name.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
                return True

        msg_str = str(message).lower()
        if "documentmessage" in msg_str and ("video/" in msg_str or ".mp4" in msg_str or ".mov" in msg_str):
            return True

        return False

    @classmethod
    def _is_plain_text(cls, message: Message) -> bool:
        """Check if message is plain text without any document or media attachments."""
        if cls._has_document_or_file(message) or cls._is_photo(message) or cls._is_video(message):
            return False

        text = cls._extract_text(message)
        return bool(text and text.strip())

    @classmethod
    def _get_str_val(cls, val: Any) -> Optional[str]:
        """Safely extract plain string from string or aiobale text/caption object."""
        if val is None:
            return None

        if isinstance(val, str):
            cleaned = val.strip()
            if not cleaned or cleaned == "None" or cleaned.startswith("content=None"):
                return None
            return cleaned

        for inner_attr in ("content", "text", "value", "raw_text", "caption", "message"):
            inner_val = getattr(val, inner_attr, None)
            if inner_val is not None:
                res = cls._get_str_val(inner_val)
                if res:
                    return res

        return None

    @classmethod
    def _extract_text(cls, obj: Any, depth: int = 0) -> str:
        """Extract text or caption from message or nested forwarded/replied messages and documents."""
        if obj is None or depth > 5:
            return ""

        for text_attr in ("caption", "text", "description"):
            val = getattr(obj, text_attr, None)
            extracted = cls._get_str_val(val)
            if extracted:
                return extracted

        child_attrs = (
            "content", "document", "photo", "photos", "video",
            "media", "attachment", "file", "replied_to",
            "quoted_replied_to", "previous_message", "message"
        )
        for attr in child_attrs:
            child = getattr(obj, attr, None)
            if child is not None:
                if isinstance(child, (list, tuple)):
                    for item in child:
                        res = cls._extract_text(item, depth + 1)
                        if res:
                            return res
                else:
                    res = cls._extract_text(child, depth + 1)
                    if res:
                        return res

        return ""

    async def _download_media(self, message: Message, media_kind: str) -> Optional[bytes]:
        """Download media file into memory using file_id and access_hash."""
        found_media = self._find_documents_and_media(message)
        if not found_media:
            logger.error("No valid media objects with file_id and access_hash found in message.")
            return None

        for doc_obj, file_id, access_hash in found_media:
            logger.info("Downloading %s using file_id=%s and access_hash=%s", media_kind, file_id, access_hash)

            if hasattr(self.client, "download_file") and callable(getattr(self.client, "download_file")):
                try:
                    res = await self.client.download_file(file_id, access_hash)
                    data = self._resolve_download_result(res)
                    if data:
                        return data
                except Exception as e:
                    logger.debug("download_file(file_id, access_hash) failed: %s", e)

                try:
                    res = await self.client.download_file(file_id=file_id, access_hash=access_hash)
                    data = self._resolve_download_result(res)
                    if data:
                        return data
                except Exception as e:
                    logger.debug("download_file(kwargs) failed: %s", e)

            if hasattr(self.client, "get_file") and callable(getattr(self.client, "get_file")):
                try:
                    file_obj = await self.client.get_file(file_id, access_hash)
                    data = self._resolve_download_result(file_obj)
                    if not data and hasattr(file_obj, "download") and callable(getattr(file_obj, "download")):
                        res = await file_obj.download()
                        data = self._resolve_download_result(res)
                    if data:
                        return data
                except Exception as e:
                    logger.debug("get_file(file_id, access_hash) failed: %s", e)

            if hasattr(doc_obj, "download") and callable(getattr(doc_obj, "download")):
                try:
                    res = await doc_obj.download()
                    data = self._resolve_download_result(res)
                    if data:
                        return data
                except Exception as e:
                    logger.debug("doc_obj.download() failed: %s", e)

        logger.error("Could not download %s media: all download methods failed.", media_kind)
        return None

    @staticmethod
    def _resolve_download_result(result: Any) -> Optional[bytes]:
        """Convert download result (file path, bytes, or buffer) to byte array."""
        if isinstance(result, bytes):
            return result
        if hasattr(result, "getvalue") and callable(getattr(result, "getvalue")):
            return result.getvalue()
        if hasattr(result, "read") and callable(getattr(result, "read")):
            data = result.read()
            if isinstance(data, bytes):
                return data
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